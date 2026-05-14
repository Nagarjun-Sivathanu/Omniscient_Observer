"""
Pipeline orchestrator.

Each hotkey is focused on exactly one job — no overlap, no cross-firing:

  F9  run_full(img)         : OCR → recall → LLM summary → Obsidian note → memory
  F10 fill_now()            : on-demand form capture+detection → cursor fill
  F11 commit_calendar()     : on-demand event extraction → stage → commit on 2nd press

Light pipeline (background poll every 30s):
  OCR → activity tracking → cheap form heuristic → store raw to SQLite
  Runs without any LLM/vision calls so it doesn't compete for the GPU.
"""
import threading
from PIL import Image
from loguru import logger

from src import ocr, llm, notes, memory, recall, form_detector, form_filler
from src import calendar_parser, calendar_writer
from src.activity import ActivityMonitor

_lock = threading.Lock()
_activity: ActivityMonitor | None = None


def set_activity_monitor(mon: ActivityMonitor) -> None:
    global _activity
    _activity = mon


def current_activity() -> tuple[str, float]:
    """Return (window_title, minutes) for the currently tracked app, or ('', 0)."""
    if _activity:
        return _activity.current_app()
    return "", 0.0


# ── Notification helper ───────────────────────────────────────────────────────

def _notify(title: str, message: str) -> None:
    # Windows balloon tooltip caps: title=63 chars, message=255 chars
    try:
        from plyer import notification
        notification.notify(
            title=title[:63],
            message=message[:255],
            app_name="Omniscient Observer",
            timeout=8,
        )
    except Exception as e:
        logger.debug(f"Notification skipped: {e}")


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_full(img: Image.Image) -> None:
    """
    F9 capture hotkey — NOTES ONLY.

    Each hotkey is now focused on a single job:
      - F9 (this)     : capture → OCR → LLM summary → Obsidian note → memory
      - F10 (fill_now): on-demand form detection and cursor fill
      - F11 (commit_calendar): on-demand event extraction and Google Calendar commit

    Calendar extraction is NOT done here — it triggers an extra LLM call that
    competes for the GPU and produces spurious notifications. The background
    light pipeline still does cheap heuristic form detection every 30s so F10
    can use staged data when available.

    Guarded by a lock — a second press while running is dropped gracefully.
    """
    if not _lock.acquire(blocking=False):
        logger.info("Full pipeline already running — skipping duplicate trigger")
        return

    try:
        app_title = ""
        if _activity:
            app_title, _ = _activity.current_app()

        # 1. OCR
        text = ocr.extract_text(img)
        if not text:
            logger.info("OCR returned empty — skipping pipeline")
            _notify("Note", "Couldn't read text from the screen.")
            return
        logger.info(f"OCR extracted {len(text)} chars from '{app_title}'")

        # 2. Recall related past context (cheap, local vector search)
        past_results = recall.recall_context(text, n=3)
        related_titles = _extract_related_titles(past_results)

        # 3. Summarise with LLM — returns (title, body)
        note_title, note_body = llm.summarize_as_note(
            text,
            window_title=app_title,
            related_notes=past_results,
        )
        if not note_body:
            logger.warning("LLM returned empty summary")
            _notify("Note", "LLM didn't return a summary (is Ollama running?).")
            return

        # 4. Write Obsidian note
        tags = ["omniscient-observer"]
        if app_title:
            safe_tag = app_title.split("-")[0].strip().lower().replace(" ", "-")[:30]
            tags.append(safe_tag)
        note_path = notes.write_note(
            title=note_title,
            body=note_body,
            source_app=app_title,
            tags=tags,
            related_titles=related_titles,
        )
        if note_path:
            _notify("Note saved", f"{note_path.name}")

        # 5. Store to memory (semantic recall + raw log)
        oid = memory.log_observation(text, summary=note_body, app=app_title, source="hotkey")
        memory.store_embedding(text, summary=note_body, app=app_title, obs_id=oid)

        logger.info("Full pipeline complete (notes only)")

    finally:
        _lock.release()


def commit_calendar() -> None:
    """
    F11 calendar hotkey workflow:
      - If events are already staged → commit them to Google Calendar.
      - If nothing is staged → capture the screen, extract events from text,
        and stage them. User presses F11 again to commit.
    """
    # Step 1: commit if already staged
    if calendar_writer.has_pending():
        summary = calendar_writer.pending_summary()
        logger.info(f"Committing calendar events:\n{summary}")
        links = calendar_writer.commit_pending()
        if links:
            _notify("Calendar events saved", f"Created {len(links)} event(s).\n{summary}")
            logger.info(f"Calendar events committed: {links}")
        else:
            logger.warning("Calendar commit returned no links — check observer.log for errors")
            _notify("Calendar", "Failed to create events — check logs (may need Google OAuth).")
        return

    # Step 2: nothing staged — capture screen and try to extract events
    logger.info("commit_calendar: no events staged — capturing screen to extract events")
    try:
        from src import capture, ocr
        img = capture.capture_screen()
        text = ocr.extract_text(img)
    except Exception as e:
        logger.error(f"commit_calendar: screen capture/OCR failed: {e}")
        _notify("Calendar", f"Screen capture failed: {e}")
        return

    if not text:
        logger.info("commit_calendar: OCR returned no text")
        _notify("Calendar", "No readable text on screen.")
        return

    events = calendar_parser.extract_events(text)
    if not events:
        logger.info("commit_calendar: no events found on current screen")
        _notify(
            "Calendar — no events found",
            "No dates or events detected on the current screen. "
            "Switch to a page with event dates and press Ctrl+Shift+F11 again.",
        )
        return

    calendar_writer.stage_events(events)
    _notify(
        f"Found {len(events)} event(s) — confirm to save",
        calendar_writer.pending_summary() +
        "\n\nPress Ctrl+Shift+F11 again to commit, or use tray menu to discard.",
    )


def discard_calendar() -> None:
    """Called by tray menu — discards staged events."""
    calendar_writer.discard_pending()
    _notify("Calendar", "Pending events discarded.")


def fill_now() -> None:
    """
    F10 fill hotkey workflow:
      - If a form is already staged → fill it at cursor (fast path).
      - If nothing staged → run an on-demand screen capture + heuristic form
        detection, then fill. Avoids the 30-second poll wait.
    """
    if form_filler.has_pending():
        form_filler.fill_at_cursor()
        return

    logger.info("fill_now: no staged form — capturing screen to detect one")
    try:
        from src import capture
        img = capture.capture_screen()
        word_boxes = ocr.extract_words_with_boxes(img)
        form = form_detector.detect(img, use_vision=False)
    except Exception as e:
        logger.error(f"fill_now: capture/detect failed: {e}")
        _notify("Form filler", f"Capture failed: {e}")
        return

    if not form:
        logger.info("fill_now: no form detected on current screen")
        _notify(
            "Form filler — no form here",
            "No form detected on the current screen. "
            "Switch to a page with a form and press Ctrl+Shift+F10 again.",
        )
        return

    form_filler.stage_form(form, word_boxes)
    logger.info(f"fill_now: staged {len(form.fields)} field(s) on demand")
    form_filler.fill_at_cursor()


# ── Light pipeline ────────────────────────────────────────────────────────────

def run_light(img: Image.Image) -> None:
    """
    Called on poll trigger. CPU-only — no LLM, no vision model.
    Logs OCR text and runs a fast form heuristic.
    """
    try:
        app_title = ""
        if _activity:
            app_title, _ = _activity.current_app()

        text = ocr.extract_text(img)
        if not text:
            return

        memory.log_observation(text, app=app_title, source="poll")

        word_boxes = ocr.extract_words_with_boxes(img)
        form = form_detector.detect(img, use_vision=False)
        if form:
            first_detection = not form_filler.has_pending()
            # Always re-stage so word_boxes stay fresh each poll cycle.
            # This prevents cursor-fill from using stale coordinates after
            # the form layout changes (fields added/removed).
            form_filler.stage_form(form, word_boxes)
            if first_detection:
                _notify(
                    "Form detected",
                    f"Fields: {', '.join(form.fields[:4])}.\n"
                    "Hover near a field label and press Ctrl+Shift+F10 to copy its value.",
                )

    except Exception as e:
        logger.error(f"Light pipeline error: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_related_titles(recall_text: str) -> list[str]:
    """
    Pull document snippets from the recall context and turn them into wikilink titles.
    Strips markdown heading markers so we don't get [[## Summary]] as a link.
    """
    import re
    titles = []
    seen = set()
    for line in recall_text.splitlines():
        m = re.match(r"- \[([^\]]+)\] (.+)", line)
        if not m:
            continue
        snippet = m.group(2).strip()
        # Strip leading '#' heading markers (## Summary → Summary)
        snippet = re.sub(r"^#+\s*", "", snippet)
        # Take the first meaningful clause (before a period or dash)
        snippet = re.split(r"[.—–]", snippet)[0].strip()
        snippet = snippet[:60]
        if snippet and snippet not in seen:
            seen.add(snippet)
            titles.append(snippet)
    return titles

"""
Pipeline orchestrator.

Full pipeline  (hotkey trigger):
  capture → OCR → recall past context → LLM summarize → write Obsidian note
           → form detection → calendar extraction (stage, wait for confirmation)
           → store to memory

Light pipeline (poll trigger):
  OCR → activity tracking → form heuristic check → store raw to SQLite
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


# ── Notification helper ───────────────────────────────────────────────────────

def _notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Omniscient Observer",
            timeout=8,
        )
    except Exception as e:
        logger.debug(f"Notification skipped: {e}")


# ── Full pipeline ─────────────────────────────────────────────────────────────

def run_full(img: Image.Image) -> None:
    """
    Called on hotkey press. Runs the complete AI pipeline.
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
            return
        logger.info(f"OCR extracted {len(text)} chars from '{app_title}'")

        # 2. Recall related past context
        past_results = recall.recall_context(text, n=3)
        # Extract just the summary snippets as related titles for wikilinks
        related_titles = _extract_related_titles(past_results)

        # 3. Summarise with LLM — returns (title, body)
        note_title, note_body = llm.summarize_as_note(
            text,
            window_title=app_title,
            related_notes=past_results,
        )
        if not note_body:
            logger.warning("LLM returned empty summary")
            return

        # 4. Write Obsidian note (content-based filename, with related wikilinks)
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

        # 5. Store to memory
        oid = memory.log_observation(text, summary=note_body, app=app_title, source="hotkey")
        memory.store_embedding(text, summary=note_body, app=app_title, obs_id=oid)

        # 6. Form detection (vision-confirmed)
        word_boxes = ocr.extract_words_with_boxes(img)
        form = form_detector.detect(img, use_vision=True)
        if form:
            form_filler.stage_form(form, word_boxes)
            _notify(
                "Form detected",
                f"Fields: {', '.join(form.fields[:4])}.\n"
                "Press Ctrl+Shift+F10 to fill field at cursor, or use tray menu.",
            )

        # 7. Calendar event extraction — stage for confirmation, never auto-commit
        events = calendar_parser.extract_events(text)
        if events:
            calendar_writer.stage_events(events)
            _notify(
                "Calendar events found — confirm to save",
                calendar_writer.pending_summary() +
                "\nPress Ctrl+Shift+F11 to commit, or use tray menu.",
            )
        else:
            logger.info("No calendar events found in screen text")

        logger.info("Full pipeline complete")

    finally:
        _lock.release()


def commit_calendar() -> None:
    """Called by calendar hotkey or tray menu — commits staged events."""
    if not calendar_writer.has_pending():
        logger.info("commit_calendar: no pending events — capture a screen with dates first")
        _notify("Calendar", "No events staged.\nFirst press Ctrl+Shift+F9 on a page showing dates/events.")
        return
    summary = calendar_writer.pending_summary()
    logger.info(f"Committing calendar events:\n{summary}")
    links = calendar_writer.commit_pending()
    if links:
        _notify("Calendar events saved", f"Created {len(links)} event(s).\n{summary}")
        logger.info(f"Calendar events committed: {links}")
    else:
        logger.warning("Calendar commit returned no links — check observer.log for errors")
        _notify("Calendar", "Failed to create events — check logs (may need Google OAuth).")


def discard_calendar() -> None:
    """Called by tray menu — discards staged events."""
    calendar_writer.discard_pending()
    _notify("Calendar", "Pending events discarded.")


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
        if form and not form_filler.has_pending():
            form_filler.stage_form(form, word_boxes)
            _notify(
                "Form detected",
                f"Fields: {', '.join(form.fields[:4])}.\n"
                "Hover near a field and press Ctrl+Shift+F10 to copy its value.",
            )

    except Exception as e:
        logger.error(f"Light pipeline error: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_related_titles(recall_text: str) -> list[str]:
    """Pull short document snippets out of the recall context for use as wikilink titles."""
    import re
    titles = []
    for line in recall_text.splitlines():
        m = re.match(r"- \[([^\]]+)\] (.+)", line)
        if m:
            snippet = m.group(2).strip()
            # Use first 60 chars of the snippet as a rough title
            titles.append(snippet[:60])
    return titles

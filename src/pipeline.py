"""
Pipeline orchestrator.

Full pipeline  (hotkey trigger):
  capture → OCR → recall past context → LLM summarize → write Obsidian note
           → form detection → calendar extraction → store to memory

Light pipeline (poll trigger):
  OCR → activity tracking → form heuristic check → store raw to SQLite
"""
import threading
from PIL import Image
from loguru import logger

from src import ocr, llm, notes, memory, recall, form_detector, form_filler
from src import calendar_parser, calendar_writer
from src.activity import ActivityMonitor

# A lock ensures we never run two full pipelines (LLM calls) at once
_lock = threading.Lock()

# Shared activity monitor instance (set by main.py)
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
        past = recall.recall_context(text, n=3)

        # 3. Summarise with LLM
        prompt_text = text
        if past:
            prompt_text = f"{past}\n\n---\nCurrent screen:\n{text}"
        summary = llm.summarize_as_note(prompt_text, window_title=app_title)
        if not summary:
            logger.warning("LLM returned empty summary")
            return

        # 4. Write Obsidian note
        tags = ["omniscient-observer"]
        if app_title:
            safe_tag = app_title.split("-")[0].strip().lower().replace(" ", "-")[:30]
            tags.append(safe_tag)
        notes.write_note(summary, source_app=app_title, tags=tags)

        # 5. Store to memory
        oid = memory.log_observation(text, summary=summary, app=app_title, source="hotkey")
        memory.store_embedding(text, summary=summary, app=app_title, obs_id=oid)

        # 6. Form detection (vision-confirmed)
        word_boxes = ocr.extract_words_with_boxes(img)
        form = form_detector.detect(img, use_vision=True)
        if form:
            form_filler.stage_form(form, word_boxes)
            _notify(
                "Form detected",
                f"Fields: {', '.join(form.fields[:4])}.\n"
                "Press Ctrl+Shift+F to fill, or use tray menu.",
            )

        # 7. Calendar event extraction
        events = calendar_parser.extract_events(text)
        if events:
            for ev in events:
                _notify("Calendar event found", f"{ev.title} — {ev.date} {ev.time}".strip())
            # Run calendar writes in background so they don't block
            threading.Thread(
                target=calendar_writer.create_events,
                args=(events,),
                daemon=True,
            ).start()

        logger.info("Full pipeline complete")

    finally:
        _lock.release()


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

        # Store raw observation to SQLite (no embedding — saves VRAM/time)
        memory.log_observation(text, app=app_title, source="poll")

        # Fast form heuristic (no vision model call)
        word_boxes = ocr.extract_words_with_boxes(img)
        form = form_detector.detect(img, use_vision=False)
        if form and not form_filler.has_pending():
            form_filler.stage_form(form, word_boxes)
            _notify(
                "Form detected",
                f"Fields: {', '.join(form.fields[:4])}.\n"
                "Press Ctrl+Shift+F to fill.",
            )

    except Exception as e:
        logger.error(f"Light pipeline error: {e}")

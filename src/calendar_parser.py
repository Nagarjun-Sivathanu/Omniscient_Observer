"""Extract calendar events from screen text using the LLM."""
from dataclasses import dataclass
from loguru import logger
from src import llm


@dataclass
class CalendarEvent:
    title: str
    date: str        # YYYY-MM-DD or ""
    time: str        # HH:MM or ""
    description: str = ""


def extract_events(ocr_text: str) -> list[CalendarEvent]:
    """
    Parse OCR text and return any calendar events/meetings found.
    Returns an empty list if nothing relevant is detected.
    """
    # Quick heuristic: skip LLM call if text has no time/date signals
    _signals = ("meeting", "appointment", "at ", "am", "pm", "monday", "tuesday",
                 "wednesday", "thursday", "friday", "saturday", "sunday",
                 "january", "february", "march", "april", "may", "june",
                 "july", "august", "september", "october", "november", "december",
                 "tomorrow", "next week", "deadline", "due", "schedule")
    lower = ocr_text.lower()
    if not any(s in lower for s in _signals):
        return []

    raw_events = llm.extract_calendar_events(ocr_text)
    events = []
    for e in raw_events:
        if not e.get("title"):
            continue
        events.append(CalendarEvent(
            title=e.get("title", "Untitled"),
            date=e.get("date", ""),
            time=e.get("time", ""),
            description=e.get("description", ""),
        ))
    if events:
        logger.info(f"Extracted {len(events)} calendar event(s) from screen")
    return events

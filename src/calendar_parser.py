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


# Broad set of signals that suggest dates/events are on screen.
# Covers English and common Indian context (counselling, allotment, entrance exams).
_DATE_SIGNALS = (
    # Time of day
    "am", "pm",
    # Day names
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # Month names
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    # Event keywords
    "meeting", "appointment", "event", "session", "interview", "exam",
    "class", "lecture", "seminar", "workshop", "webinar", "conference",
    # Deadline/schedule keywords (including Indian admission contexts)
    "deadline", "due date", "last date", "schedule", "timetable",
    "tomorrow", "next week", "this week", "today",
    "counselling", "counseling", "allotment", "registration closes",
    "result", "admit card", "hall ticket", "reporting",
    # Year patterns (broad — catches "2025", "2026", "2027")
    "2025", "2026", "2027",
    # Date pattern fragments
    "/2025", "/2026", "-2025", "-2026",
)


def extract_events(ocr_text: str) -> list[CalendarEvent]:
    """
    Parse OCR text and return calendar events/deadlines found.
    Uses a broad signal set so admission pages, exam schedules, etc. are caught.
    """
    lower = ocr_text.lower()
    matched_signals = [s for s in _DATE_SIGNALS if s in lower]
    if not matched_signals:
        logger.debug("Calendar parser: no date signals found, skipping LLM")
        return []

    logger.info(f"Calendar parser: date signals found → {matched_signals[:5]}")
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
    else:
        logger.info("Calendar parser: LLM found no structured events in text")
    return events


def parse_manual_event(text: str) -> CalendarEvent | None:
    """
    Parse a free-text description of an event (e.g. from clipboard).
    Returns a CalendarEvent or None if nothing parseable.
    Example input: "Team meeting Friday 3pm about the project"
    """
    if not text or len(text.strip()) < 5:
        return None
    raw = llm.extract_calendar_events(text)
    if raw and raw[0].get("title"):
        e = raw[0]
        return CalendarEvent(
            title=e.get("title", text[:50]),
            date=e.get("date", ""),
            time=e.get("time", ""),
            description=e.get("description", ""),
        )
    # Fallback: treat the whole text as the event title with today's date
    from datetime import date
    return CalendarEvent(title=text[:80].strip(), date=str(date.today()), time="", description="")

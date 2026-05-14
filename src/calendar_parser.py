"""Extract calendar events from screen text using the LLM."""
import re
from dataclasses import dataclass
from loguru import logger
from src import llm


@dataclass
class CalendarEvent:
    title: str
    date: str        # YYYY-MM-DD or ""
    time: str        # HH:MM or ""
    description: str = ""


# Signals that suggest dates/events are on screen.
# All checked as whole words (word-boundary regex) to avoid substring false positives
# — "am" in "camera", "may" in "display", "pm" in "implement" would all match without \b.
_DATE_SIGNALS = (
    # Day names
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    # Month names (exclude "may" — too common as a verb/auxiliary)
    "january", "february", "march", "april", "june",
    "july", "august", "september", "october", "november", "december",
    # Time-of-day (full words only, not "pm" in "implement")
    "a.m.", "p.m.", "a.m", "p.m",
    # Event keywords
    "meeting", "appointment", "event", "session", "interview", "exam",
    "lecture", "seminar", "workshop", "webinar", "conference",
    # Deadline/schedule keywords (including Indian admission contexts)
    "deadline", "schedule", "timetable", "tomorrow",
    "counselling", "counseling", "allotment",
    "admit card", "hall ticket",
    # Year patterns — digit strings, safe to use `in` since digits don't appear in words
    "2025", "2026", "2027",
)

# Signals matched with word boundaries (re.search for whole-word match)
_WORD_SIGNALS = frozenset(s for s in _DATE_SIGNALS if not s[0].isdigit())
# Digit signals are safe with plain substring match
_DIGIT_SIGNALS = frozenset(s for s in _DATE_SIGNALS if s[0].isdigit())

# Minimum distinct signals required before calling the LLM.
# Prevents single-word false positives (e.g. "schedule" in a nav bar with no dates).
_MIN_SIGNALS = 2


def _count_signals(lower: str) -> list[str]:
    """Return matched date signal words using word-boundary matching."""
    matched = []
    for s in _WORD_SIGNALS:
        if re.search(r"\b" + re.escape(s) + r"\b", lower):
            matched.append(s)
    for s in _DIGIT_SIGNALS:
        if s in lower:
            matched.append(s)
    return matched


def extract_events(ocr_text: str) -> list[CalendarEvent]:
    """
    Parse OCR text and return calendar events/deadlines found.
    Requires at least _MIN_SIGNALS whole-word date signals before calling the LLM,
    preventing false positives from generic screen text.
    """
    lower = ocr_text.lower()
    matched_signals = _count_signals(lower)
    if len(matched_signals) < _MIN_SIGNALS:
        logger.debug(f"Calendar parser: only {len(matched_signals)} signal(s) found ({matched_signals}), skipping LLM")
        return []

    logger.info(f"Calendar parser: {len(matched_signals)} date signals → {matched_signals[:5]}")
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

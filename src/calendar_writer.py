"""
Google Calendar writer with user-confirmation flow.

Setup (one-time):
  1. Go to https://console.cloud.google.com
  2. Create a project → enable "Google Calendar API"
  3. Create OAuth 2.0 credentials (Desktop app) → download as client_secret.json
  4. Place client_secret.json in the project root
  5. First run will open a browser for consent → token.pickle is saved for reuse

Confirmation flow:
  - Detected events are staged (never auto-committed).
  - User sees a tray notification with the event summary.
  - Press Ctrl+Alt+Shift+C (or tray menu) to commit, or discard via tray.
  - If client_secret.json is missing, falls back to local .ics files.
"""
import pickle
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
import uuid
from loguru import logger

from src.calendar_parser import CalendarEvent
from src.config import CALENDAR_NAME, CALENDAR_FALLBACK

_ROOT               = Path(__file__).parent.parent
_SECRET_FILE        = _ROOT / "client_secret.json"
_TOKEN_FILE         = _ROOT / "token.pickle"
_SCOPES             = ["https://www.googleapis.com/auth/calendar.events"]
_LOCAL_CALENDAR_DIR = _ROOT / "data" / "calendar"

# Pending events waiting for user confirmation
_pending_events: list[CalendarEvent] = []


def _get_service():
    """Return an authenticated Google Calendar service object, or raise."""
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if _TOKEN_FILE.exists():
        with open(_TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _SECRET_FILE.exists():
                raise FileNotFoundError(
                    "client_secret.json not found. "
                    "Download it from Google Cloud Console and place it in the project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_SECRET_FILE), _SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("calendar", "v3", credentials=creds)


def _get_calendar_id(svc) -> str:
    """Return the calendar ID matching CALENDAR_NAME. Falls back to 'primary' if allowed."""
    try:
        items = svc.calendarList().list().execute().get("items", [])
        for cal in items:
            if cal.get("summary", "").lower() == CALENDAR_NAME.lower():
                logger.info(f"Using calendar: {cal['summary']} ({cal['id']})")
                return cal["id"]
        logger.warning(f"Calendar '{CALENDAR_NAME}' not found in your Google Calendar list.")
    except Exception as e:
        logger.error(f"Calendar list lookup failed: {e}")

    if CALENDAR_FALLBACK:
        logger.warning("Falling back to primary calendar.")
        return "primary"
    logger.error(
        f"Calendar '{CALENDAR_NAME}' not found and fallback_to_primary=false. "
        "Create the calendar in Google Calendar first, or set fallback_to_primary=true."
    )
    return ""


# ── Pending / confirmation ────────────────────────────────────────────────────

def stage_events(events: list[CalendarEvent]) -> None:
    """Stage events for user confirmation. Does NOT write to calendar yet."""
    global _pending_events
    _pending_events = list(events)
    logger.info(f"Staged {len(events)} calendar event(s) for confirmation")


def has_pending() -> bool:
    return bool(_pending_events)


def pending_summary() -> str:
    if not _pending_events:
        return "No pending events."
    lines = []
    for ev in _pending_events:
        when = f"{ev.date} {ev.time}".strip() or "date TBD"
        lines.append(f"• {ev.title} — {when}")
    return "\n".join(lines)


def commit_pending() -> list[str]:
    """Write all staged events to Google Calendar. Clears the queue."""
    global _pending_events
    if not _pending_events:
        logger.info("No pending calendar events to commit")
        return []
    events = list(_pending_events)
    _pending_events = []
    return create_events(events)


def discard_pending() -> None:
    global _pending_events
    _pending_events = []
    logger.info("Pending calendar events discarded")


def _build_body(event: CalendarEvent) -> dict:
    """Convert CalendarEvent to Google Calendar API event body."""
    if event.date:
        try:
            d = datetime.strptime(event.date, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
    else:
        d = date.today()

    if event.time:
        try:
            t = datetime.strptime(event.time, "%H:%M").time()
        except ValueError:
            t = None
    else:
        t = None

    if t:
        # Use UTC timezone-aware datetime
        start_dt = datetime.combine(d, t).replace(tzinfo=timezone.utc)
        end_dt = datetime.combine(d, (t.replace(hour=(t.hour + 1) % 24) if t.hour < 23 else t.replace(hour=23, minute=59))).replace(tzinfo=timezone.utc)
        return {
            "summary":     event.title,
            "description": event.description,
            "start": {"dateTime": start_dt.isoformat()},
            "end":   {"dateTime": end_dt.isoformat()},
        }
    else:
        return {
            "summary":     event.title,
            "description": event.description,
            "start": {"date": d.isoformat()},
            "end":   {"date": d.isoformat()},
        }


def _ensure_local_calendar_dir() -> None:
    _LOCAL_CALENDAR_DIR.mkdir(parents=True, exist_ok=True)


def _format_ics_event(event: CalendarEvent) -> str:
    uid = uuid.uuid4().hex
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    if event.date:
        try:
            d = datetime.strptime(event.date, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
    else:
        d = date.today()

    if event.time:
        try:
            t = datetime.strptime(event.time, "%H:%M").time()
        except ValueError:
            t = None
    else:
        t = None

    if t:
        dtstart = datetime.combine(d, t).strftime("%Y%m%dT%H%M%S")
        dtend = (datetime.combine(d, t.replace(hour=(t.hour + 1) % 24)).strftime("%Y%m%dT%H%M%S")
                 if t.hour < 23 else datetime.combine(d, t.replace(hour=23, minute=59)).strftime("%Y%m%dT%H%M%S"))
        body = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
        ]
    else:
        body = [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
        ]

    body += [
        f"SUMMARY:{event.title}",
        f"DESCRIPTION:{event.description}",
        "END:VEVENT",
    ]
    return "\n".join(body) + "\n"


def _write_local_ics(events: list[CalendarEvent]) -> str:
    _ensure_local_calendar_dir()
    path = _LOCAL_CALENDAR_DIR / f"events-{datetime.now().strftime('%Y%m%d-%H%M%S')}.ics"
    contents = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Omniscient Observer//EN",
    ]
    for event in events:
        contents.append(_format_ics_event(event))
    contents.append("END:VCALENDAR")
    path.write_text("\n".join(contents), encoding="utf-8")
    logger.info(f"Local calendar file written: {path}")
    return str(path)


def create_event(event: CalendarEvent) -> str | None:
    """
    Create a Google Calendar event. Returns the event HTML link or None on failure.
    Requires client_secret.json in project root.
    """
    try:
        svc    = _get_service()
        cal_id = _get_calendar_id(svc)
        if not cal_id:
            logger.warning("No target calendar — falling back to local .ics")
            return _write_local_ics([event])
        body   = _build_body(event)
        result = svc.events().insert(calendarId=cal_id, body=body).execute()
        link = result.get("htmlLink", "")
        logger.info(f"Calendar event created: {event.title} → {link}")
        return link
    except (FileNotFoundError, ModuleNotFoundError, ImportError) as e:
        logger.warning(f"Google Calendar unavailable: {e} — falling back to local .ics file")
        return _write_local_ics([event])
    except Exception as e:
        logger.error(f"Google Calendar create failed: {e}")
        return None


def create_events(events: list[CalendarEvent]) -> list[str]:
    """Create multiple events. Returns list of HTML links or local .ics file paths."""
    if not events:
        return []
    links = []
    for ev in events:
        link = create_event(ev)
        if link:
            links.append(link)
    if not links:
        return [_write_local_ics(events)]
    return links

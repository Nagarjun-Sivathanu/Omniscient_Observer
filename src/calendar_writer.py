"""
Google Calendar writer.

Setup (one-time):
  1. Go to https://console.cloud.google.com
  2. Create a project → enable "Google Calendar API"
  3. Create OAuth 2.0 credentials (Desktop app) → download as client_secret.json
  4. Place client_secret.json in the project root
  5. First run will open a browser for consent → token.pickle is saved for reuse
"""
import os
import pickle
from datetime import datetime, date
from pathlib import Path
from loguru import logger

from src.calendar_parser import CalendarEvent

_ROOT          = Path(__file__).parent.parent
_SECRET_FILE   = _ROOT / "client_secret.json"
_TOKEN_FILE    = _ROOT / "token.pickle"
_SCOPES        = ["https://www.googleapis.com/auth/calendar.events"]


def _get_service():
    """Return an authenticated Google Calendar service object."""
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
        start_dt = datetime.combine(d, t)
        end_dt   = datetime.combine(d, t.replace(hour=(t.hour + 1) % 24))
        return {
            "summary":     event.title,
            "description": event.description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "local"},
            "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "local"},
        }
    else:
        return {
            "summary":     event.title,
            "description": event.description,
            "start": {"date": d.isoformat()},
            "end":   {"date": d.isoformat()},
        }


def create_event(event: CalendarEvent) -> str | None:
    """
    Create a Google Calendar event. Returns the event HTML link or None on failure.
    Requires client_secret.json in project root.
    """
    try:
        svc  = _get_service()
        body = _build_body(event)
        result = svc.events().insert(calendarId="primary", body=body).execute()
        link = result.get("htmlLink", "")
        logger.info(f"Calendar event created: {event.title} → {link}")
        return link
    except FileNotFoundError as e:
        logger.warning(str(e))
        return None
    except Exception as e:
        logger.error(f"Google Calendar create failed: {e}")
        return None


def create_events(events: list[CalendarEvent]) -> list[str]:
    """Create multiple events. Returns list of HTML links (skips failures)."""
    links = []
    for ev in events:
        link = create_event(ev)
        if link:
            links.append(link)
    return links

"""
Local web dashboard at http://localhost:8765

Serves a single static HTML page that reads from JSON endpoints:
  GET /api/now           current activity (live)
  GET /api/today         today's category totals + top apps
  GET /api/notes/today   today's Obsidian notes
  GET /api/calendar      staged calendar events awaiting confirmation
  GET /api/health        sanity check

The HTML/JS lives in static/index.html and uses Tailwind + Alpine + Chart.js
via CDN so there is no build step.

Runs as a daemon thread alongside the tray icon and hotkey listener.
"""
import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from loguru import logger

from src import memory, notes, calendar_writer, status
from src import pipeline as _pipeline

PORT = 8765
_STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Omniscient Observer", docs_url=None, redoc_url=None)


@app.get("/")
def index():
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/now")
def now():
    title, minutes = _pipeline.current_activity()
    return {"title": title, "minutes": round(minutes, 1)}


@app.get("/api/today")
def today():
    cats = memory.daily_category_totals()
    apps = memory.daily_activity_summary()
    total = sum(cats.values())
    return {
        "total_seconds":   total,
        "categories":      cats,
        "top_apps":        apps[:10],
    }


@app.get("/api/notes/today")
def notes_today():
    return {"notes": notes.list_notes_today()}


@app.get("/api/calendar")
def calendar_pending():
    events = []
    for ev in calendar_writer._pending_events:
        events.append({
            "title":       ev.title,
            "date":        ev.date,
            "time":        ev.time,
            "description": ev.description,
        })
    return {"pending": events}


@app.get("/api/status")
def status_endpoint():
    """Current pipeline stage (what the observer is doing right now)."""
    return status.get()


@app.get("/api/events")
def events_endpoint():
    """Last 20 stage transitions + toasts, newest first."""
    return {"events": status.recent_events(limit=20)}


@app.get("/api/skills")
def skills_endpoint(days: int = 30):
    """Skill graph (nodes + co-occurrence edges) over the last `days` days."""
    return memory.skill_graph(days=days, max_nodes=25)


@app.get("/api/week")
def week():
    """Last 7 days of daily category totals + streak + best day."""
    daily = memory.weekly_daily_totals(days=7)
    return {
        "daily":   daily,
        "top_apps":      memory.weekly_top_apps(days=7, limit=10),
        "streak":        memory.productive_streak(min_seconds=3600),
        "best_day":      memory.best_day_in_window(category="productive", days=30),
    }


def _serve():
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except Exception as e:
        logger.error(f"Dashboard server crashed: {e}")


def start() -> threading.Thread:
    t = threading.Thread(target=_serve, daemon=True, name="dashboard")
    t.start()
    logger.info(f"Dashboard server starting at http://localhost:{PORT}")
    return t


def open_in_browser() -> None:
    webbrowser.open(f"http://localhost:{PORT}")

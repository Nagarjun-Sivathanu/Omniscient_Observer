"""
Global pipeline status — what the observer is doing right now.

Each pipeline stage calls set(stage, detail, function) when it enters a step.
The dashboard polls get() to render a live "Now running…" banner.

All access is lock-guarded so the poll thread and hotkey threads don't race.
"""
import threading
import time
from collections import deque

_lock = threading.Lock()
_state = {
    "stage":    "idle",   # idle, capturing, ocr, llm, writing, calendar, fill, error
    "detail":   "",       # human-readable substep ("Reading screen text…")
    "function": "",       # which trigger: "F9 — note", "F10 — fill", "F11 — calendar", "poll"
    "started":  0.0,      # time.monotonic() at stage entry; 0 when idle
}

# Recent events ring buffer — shown in dashboard "Activity" feed.
# Each entry: {"ts": iso8601, "kind": "toast"|"stage", "title": str, "detail": str, "level": str}
_EVENTS_MAX = 50
_events: "deque[dict]" = deque(maxlen=_EVENTS_MAX)


def set(stage: str, detail: str = "", function: str = "") -> None:
    """Update the global pipeline state. Pass stage='idle' to clear."""
    from datetime import datetime
    with _lock:
        if stage == "idle":
            _state.update(stage="idle", detail="", function="", started=0.0)
        else:
            _state["stage"] = stage
            if detail:
                _state["detail"] = detail
            if function:
                _state["function"] = function
            if _state["started"] == 0.0:
                _state["started"] = time.monotonic()
            _events.append({
                "ts":     datetime.now().isoformat(timespec="seconds"),
                "kind":   "stage",
                "title":  function or stage,
                "detail": detail or stage,
                "level":  "info",
            })


def get() -> dict:
    """Return a snapshot of current status + computed elapsed seconds."""
    with _lock:
        s = dict(_state)
    s["elapsed"] = (time.monotonic() - s["started"]) if s["started"] else 0
    return s


def log_toast(title: str, detail: str = "", level: str = "info") -> None:
    """Append an event for the dashboard feed (called by overlay.push)."""
    from datetime import datetime
    with _lock:
        _events.append({
            "ts":     datetime.now().isoformat(timespec="seconds"),
            "kind":   "toast",
            "title":  title,
            "detail": detail,
            "level":  level,
        })


def recent_events(limit: int = 20) -> list[dict]:
    """Return the last N events, newest first."""
    with _lock:
        items = list(_events)
    return list(reversed(items))[:limit]

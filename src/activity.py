"""
Window activity tracker.
Polls the active window title every few seconds, accumulates time per app,
and fires a callback when the user has been on one app too long.
Persists per-app time snapshots to SQLite on every heartbeat so daily
totals survive process restarts.
"""
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
import win32gui
import win32process
import psutil

from src.config import ALERT_MINUTES
from src import memory

POLL_SECS      = 5    # how often to sample the active window
_HEARTBEAT_SECS = 300  # log activity status + persist snapshots every 5 minutes


# ── Categorisation ────────────────────────────────────────────────────────────
# Lightweight keyword-based classifier. Matches process name first, then falls
# back to window title. Keep lists short — most apps live in just one bucket.
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "productive":   ("code.exe", "pycharm", "intellij", "sublime", "vim", "emacs",
                     "obsidian", "notion", "atom", "rider", "webstorm",
                     "github", "stackoverflow", "docs.python", "developer.mozilla",
                     "visual studio", "powershell", "terminal", "wsl", "cmd.exe"),
    "communication":("slack", "discord", "teams", "outlook", "thunderbird",
                     "whatsapp", "telegram", "zoom", "skype", "gmail"),
    "media":        ("youtube", "netflix", "twitch", "crunchyroll", "spotify",
                     "vlc", "mpc", "prime video", "hulu", "disney"),
    "browsing":     ("chrome", "firefox", "msedge", "opera", "safari", "brave",
                     "google search"),
    "system":       ("explorer.exe", "settings", "taskmgr", "control panel",
                     "device manager", "file explorer"),
}


def categorize(app_key: str, title: str = "") -> str:
    """Classify an (app_key, window_title) pair into a coarse category."""
    haystack = (app_key + " " + title).lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            return category
    return "other"


@dataclass
class AppSession:
    title: str
    start: datetime = field(default_factory=datetime.now)
    seconds: float = 0.0


class ActivityMonitor:
    def __init__(self, alert_callback=None):
        """
        alert_callback(title, minutes): called when user exceeds ALERT_MINUTES
        on the same window.
        """
        self._cb = alert_callback
        self._sessions: dict[str, AppSession] = {}
        self._current: str | None = None
        self._last_sample: datetime = datetime.now()
        self._alerted: set[str] = set()
        self._lock = threading.Lock()
        # Per-app seconds already persisted to SQLite this process — diff
        # against current AppSession.seconds to compute the delta for each
        # heartbeat snapshot (append-only, no double counting).
        self._persisted_seconds: dict[str, float] = {}

    def get_active_window(self) -> tuple[str, str]:
        """Return (window_title, process_name) of the foreground window."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_name = psutil.Process(pid).name()
            return title, proc_name
        except Exception:
            return "", ""

    def _tick(self):
        now = datetime.now()
        elapsed = (now - self._last_sample).total_seconds()
        self._last_sample = now

        title, proc = self.get_active_window()
        if not title:
            return

        key = proc or title[:40]
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = AppSession(title=title)
            self._sessions[key].seconds += elapsed

            minutes = self._sessions[key].seconds / 60
            if minutes >= ALERT_MINUTES and key not in self._alerted:
                self._alerted.add(key)
                logger.info(f"Activity alert: {title} — {minutes:.0f} min")
                if self._cb:
                    self._cb(title, minutes)

            # If user switched apps, reset the alert flag for old apps
            if self._current and self._current != key:
                self._alerted.discard(self._current)
            self._current = key

    def current_app(self) -> tuple[str, float]:
        """Return (window_title, minutes_on_app) for the active session."""
        with self._lock:
            if not self._current:
                return "", 0.0
            s = self._sessions.get(self._current)
            if s is None:
                return "", 0.0
            return s.title, s.seconds / 60

    def flush_pending_snapshot(self) -> None:
        """Force-persist the current session deltas without waiting for the
        next heartbeat. Useful so tray queries see fresh totals."""
        self._heartbeat()

    def start(self) -> threading.Thread:
        def _loop():
            ticks_since_heartbeat = 0
            heartbeat_every = max(1, int(_HEARTBEAT_SECS / POLL_SECS))
            while True:
                try:
                    self._tick()
                    ticks_since_heartbeat += 1
                    if ticks_since_heartbeat >= heartbeat_every:
                        ticks_since_heartbeat = 0
                        self._heartbeat()
                except Exception as e:
                    logger.error(f"Activity tick error: {e}")
                time.sleep(POLL_SECS)

        t = threading.Thread(target=_loop, daemon=True, name="activity-monitor")
        t.start()
        logger.info("Activity monitor started")
        return t

    def _heartbeat(self) -> None:
        """Log status + persist per-app deltas to SQLite (every 5 min)."""
        title, minutes = self.current_app()
        if title:
            logger.info(f"[Activity] '{title}' — {minutes:.1f} min on current session")
        else:
            logger.info("[Activity] No active window tracked")

        with self._lock:
            for key, session in self._sessions.items():
                already = self._persisted_seconds.get(key, 0.0)
                delta   = session.seconds - already
                if delta <= 0:
                    continue
                category = categorize(key, session.title)
                try:
                    memory.log_activity_snapshot(
                        app_key=key,
                        title=session.title,
                        category=category,
                        seconds=delta,
                    )
                    self._persisted_seconds[key] = session.seconds
                except Exception as e:
                    logger.error(f"Activity snapshot persist failed for '{key}': {e}")

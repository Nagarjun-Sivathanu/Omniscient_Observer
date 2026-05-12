"""
Window activity tracker.
Polls the active window title every few seconds, accumulates time per app,
and fires a callback when the user has been on one app too long.
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

POLL_SECS = 5   # how often to sample the active window


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

    def start(self) -> threading.Thread:
        def _loop():
            while True:
                try:
                    self._tick()
                except Exception as e:
                    logger.error(f"Activity tick error: {e}")
                time.sleep(POLL_SECS)

        t = threading.Thread(target=_loop, daemon=True, name="activity-monitor")
        t.start()
        logger.info("Activity monitor started")
        return t

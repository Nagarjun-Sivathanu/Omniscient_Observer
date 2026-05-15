"""
Bottom-right toast overlay using tkinter — replaces plyer system balloons.

Why not plyer:
  - Title cap 63 chars, body cap 255 chars (we hit ValueError on long messages)
  - Old-style Windows balloon look, easy to miss
  - No control over position, duration, or styling

This module:
  - Runs a dedicated tkinter thread with a queue
  - Toasts render as borderless dark cards at bottom-right of the primary monitor
  - Fade in/out, auto-dismiss after duration_ms
  - At most one toast visible at a time (newer toast replaces older)
  - Falls back to plyer if tkinter fails to start (e.g. no display)
  - Every push is also logged to status.log_toast so the dashboard feed sees it
"""
import queue
import threading
import time
from dataclasses import dataclass, field
from loguru import logger

from src import status


@dataclass
class Toast:
    title:        str
    message:      str = ""
    level:        str = "info"        # info | success | warning | error
    duration_ms:  int = 5000
    pushed_at:    float = field(default_factory=time.monotonic)


_queue: "queue.Queue[Toast]" = queue.Queue()
_started = False
_fallback_plyer = False


def push(title: str, message: str = "", level: str = "info", duration_ms: int = 5000) -> None:
    """Show a toast at the bottom-right of the primary monitor."""
    status.log_toast(title, message, level)
    if _fallback_plyer or not _started:
        _plyer_fallback(title, message)
        return
    try:
        _queue.put_nowait(Toast(title=title, message=message, level=level, duration_ms=duration_ms))
    except Exception as e:
        logger.debug(f"Toast queue push failed: {e}")
        _plyer_fallback(title, message)


def _plyer_fallback(title: str, message: str) -> None:
    """Use the old plyer balloon when tkinter is unavailable."""
    try:
        from plyer import notification
        notification.notify(
            title=title[:63],
            message=message[:255],
            app_name="Omniscient Observer",
            timeout=6,
        )
    except Exception as e:
        logger.debug(f"Plyer fallback failed: {e}")


# Colors keyed by level — kept consistent with the dashboard palette
_LEVEL_ACCENT = {
    "info":    "#6aa9ff",
    "success": "#5dd39e",
    "warning": "#ffaa5e",
    "error":   "#ff6e6e",
}

_BG          = "#161b22"
_FG_TITLE    = "#ffffff"
_FG_BODY     = "#c9d1d9"
_TOAST_W     = 380
_MARGIN_X    = 24
_MARGIN_Y    = 80     # leave room above the Windows taskbar


def _run_tk_loop() -> None:
    """Owns the single tkinter Tk() root. Polls _queue and renders toasts."""
    global _fallback_plyer
    try:
        import tkinter as tk
    except Exception as e:
        logger.warning(f"tkinter unavailable, falling back to plyer: {e}")
        _fallback_plyer = True
        return

    try:
        root = tk.Tk()
    except Exception as e:
        logger.warning(f"tkinter Tk() failed, falling back to plyer: {e}")
        _fallback_plyer = True
        return

    root.withdraw()  # hide invisible root

    current_window = {"win": None, "dismiss_at": 0.0}

    def dismiss_current() -> None:
        w = current_window["win"]
        if w is None:
            return
        try:
            w.destroy()
        except Exception:
            pass
        current_window["win"] = None
        current_window["dismiss_at"] = 0.0

    def fade(win, start: float, end: float, step_ms: int = 16, total_ms: int = 180) -> None:
        steps = max(1, total_ms // step_ms)
        delta = (end - start) / steps

        def _step(i: int = 0, alpha: float = start):
            if i >= steps:
                try:
                    win.attributes("-alpha", end)
                    if end <= 0.01:
                        win.destroy()
                except Exception:
                    pass
                return
            try:
                win.attributes("-alpha", max(0.0, min(1.0, alpha)))
            except Exception:
                return
            win.after(step_ms, lambda: _step(i + 1, alpha + delta))

        _step()

    def show_toast(toast: Toast) -> None:
        dismiss_current()

        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.configure(bg=_BG)

        accent = _LEVEL_ACCENT.get(toast.level, _LEVEL_ACCENT["info"])

        outer = tk.Frame(win, bg=_BG)
        outer.pack(fill="both", expand=True)

        strip = tk.Frame(outer, bg=accent, width=4)
        strip.pack(side="left", fill="y")

        content = tk.Frame(outer, bg=_BG, padx=16, pady=12)
        content.pack(side="left", fill="both", expand=True)

        title_lbl = tk.Label(
            content,
            text=toast.title,
            bg=_BG, fg=_FG_TITLE,
            font=("Segoe UI", 11, "bold"),
            anchor="w", justify="left",
            wraplength=_TOAST_W - 60,
        )
        title_lbl.pack(anchor="w", fill="x")

        if toast.message:
            msg_lbl = tk.Label(
                content,
                text=toast.message,
                bg=_BG, fg=_FG_BODY,
                font=("Segoe UI", 10),
                anchor="w", justify="left",
                wraplength=_TOAST_W - 60,
            )
            msg_lbl.pack(anchor="w", fill="x", pady=(4, 0))

        # Click anywhere to dismiss
        def _on_click(_event=None):
            dismiss_current()
        for widget in (win, outer, content, strip, title_lbl):
            widget.bind("<Button-1>", _on_click)
        if toast.message:
            msg_lbl.bind("<Button-1>", _on_click)

        win.update_idletasks()
        h = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = sw - _TOAST_W - _MARGIN_X
        y = sh - h - _MARGIN_Y
        win.geometry(f"{_TOAST_W}x{h}+{x}+{y}")

        current_window["win"] = win
        current_window["dismiss_at"] = time.monotonic() + toast.duration_ms / 1000.0

        fade(win, 0.0, 0.96)

    def poll() -> None:
        try:
            while True:
                toast = _queue.get_nowait()
                show_toast(toast)
        except queue.Empty:
            pass
        # Auto-dismiss if current toast's time is up
        now = time.monotonic()
        if current_window["win"] is not None and now >= current_window["dismiss_at"] > 0:
            w = current_window["win"]
            current_window["win"] = None
            current_window["dismiss_at"] = 0.0
            try:
                fade(w, 0.96, 0.0)
            except Exception:
                try:
                    w.destroy()
                except Exception:
                    pass
        root.after(100, poll)

    poll()
    try:
        root.mainloop()
    except Exception as e:
        logger.warning(f"tkinter mainloop ended: {e}")
        _fallback_plyer = True


def start() -> threading.Thread:
    """Spin up the tkinter thread. Safe to call once at app startup."""
    global _started
    if _started:
        return threading.current_thread()
    _started = True
    t = threading.Thread(target=_run_tk_loop, daemon=True, name="overlay")
    t.start()
    logger.info("Overlay notifications started (tkinter toast)")
    return t

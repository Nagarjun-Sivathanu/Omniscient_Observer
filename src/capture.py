"""Screen capture, global hotkeys, and change detection.

Hotkeys (configured in config.toml):
  Ctrl+Shift+F9  — capture screen + run full AI pipeline
  Ctrl+Shift+F10 — fill detected form (clipboard paste mode)
  Ctrl+Shift+F11 — commit staged calendar events
"""
import hashlib
import threading
from typing import Callable
from PIL import Image
import mss
from pynput import keyboard
from loguru import logger

from src.config import HOTKEY_CAPTURE, HOTKEY_FILL, HOTKEY_CALENDAR, CHANGE_THRESH

_paused = False
_last_hash: str | None = None


def set_paused(state: bool) -> None:
    global _paused
    _paused = state
    logger.info(f"Observer {'paused' if state else 'resumed'}")


def is_paused() -> bool:
    return _paused


def capture_screen() -> Image.Image:
    with mss.MSS() as sct:
        shot = sct.grab(sct.monitors[1])
        return Image.frombytes("RGB", shot.size, shot.rgb)


def has_changed(img: Image.Image) -> bool:
    """Return True if the screen has changed from the last seen frame."""
    global _last_hash
    thumb = img.resize((64, 64)).convert("L")
    h = hashlib.md5(thumb.tobytes()).hexdigest()
    changed = h != _last_hash
    _last_hash = h
    return changed


def start_hotkey_listener(
    full_pipeline_fn: Callable,
    fill_fn: Callable,
    calendar_fn: Callable,
) -> keyboard.GlobalHotKeys:
    """
    Start a global hotkey listener using pynput.GlobalHotKeys.
    This is more reliable on Windows than the Listener+HotKey approach
    because function keys don't conflict with AltGr or IME combos.
    Returns the running GlobalHotKeys thread.
    """

    def _on_capture():
        if _paused:
            return
        logger.info("Capture hotkey pressed")
        try:
            img = capture_screen()
            # Run pipeline in a background thread so hotkey thread stays responsive
            threading.Thread(
                target=full_pipeline_fn,
                args=(img,),
                daemon=True,
                name="full-pipeline",
            ).start()
        except Exception as e:
            logger.error(f"Hotkey capture failed: {e}")

    def _on_fill():
        if _paused:
            return
        logger.info("Fill hotkey pressed")
        try:
            fill_fn()
        except Exception as e:
            logger.error(f"Fill hotkey failed: {e}")

    def _on_calendar():
        if _paused:
            return
        logger.info("Calendar hotkey pressed")
        try:
            calendar_fn()
        except Exception as e:
            logger.error(f"Calendar hotkey failed: {e}")

    hotkeys = {
        HOTKEY_CAPTURE:  _on_capture,
        HOTKEY_FILL:     _on_fill,
        HOTKEY_CALENDAR: _on_calendar,
    }

    listener = keyboard.GlobalHotKeys(hotkeys)
    listener.daemon = True
    listener.start()
    logger.info(
        f"Hotkeys active — capture: {HOTKEY_CAPTURE}  "
        f"fill: {HOTKEY_FILL}  calendar: {HOTKEY_CALENDAR}"
    )
    return listener


def start_polling(interval: int, light_pipeline_fn: Callable) -> threading.Thread:
    """Poll screen every `interval` seconds; run light pipeline if screen changed."""
    import time

    def _loop():
        while True:
            if not _paused:
                try:
                    img = capture_screen()
                    if has_changed(img):
                        light_pipeline_fn(img)
                except Exception as e:
                    logger.error(f"Poll error: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name="poll-loop")
    t.start()
    logger.info(f"Polling started (every {interval}s)")
    return t

"""Screen capture, hotkey listener, and change detection."""
import hashlib
import threading
from typing import Callable
from PIL import Image
import mss
from pynput import keyboard
from loguru import logger

from src.config import HOTKEY_CAPTURE, HOTKEY_FILL, CHANGE_THRESH

_paused = False
_last_hash: str | None = None
_full_callback: Callable | None = None   # hotkey → full pipeline
_fill_callback: Callable | None = None   # fill hotkey


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
    """Return True if screen differs from the last seen frame by > threshold."""
    global _last_hash
    thumb = img.resize((64, 64)).convert("L")
    h = hashlib.md5(thumb.tobytes()).hexdigest()
    changed = h != _last_hash
    _last_hash = h
    return changed


def _make_listener(on_full: Callable, on_fill: Callable) -> keyboard.Listener:
    hk_full = keyboard.HotKey(keyboard.HotKey.parse(HOTKEY_CAPTURE), on_full)
    hk_fill = keyboard.HotKey(keyboard.HotKey.parse(HOTKEY_FILL), on_fill)

    def on_press(key):
        try:
            hk_full.press(key)
        except Exception:
            pass
        try:
            hk_fill.press(key)
        except Exception:
            pass

    def on_release(key):
        try:
            hk_full.release(key)
        except Exception:
            pass
        try:
            hk_fill.release(key)
        except Exception:
            pass

    return keyboard.Listener(on_press=on_press, on_release=on_release)


def start_hotkey_listener(full_pipeline_fn: Callable, fill_fn: Callable) -> keyboard.Listener:
    """Start global hotkey listener in a daemon thread."""

    def _on_capture():
        if _paused:
            return
        logger.info("Capture hotkey pressed")
        try:
            img = capture_screen()
            full_pipeline_fn(img)
        except Exception as e:
            logger.error(f"Hotkey capture failed: {e}")

    def _on_fill():
        if _paused:
            return
        try:
            fill_fn()
        except Exception as e:
            logger.error(f"Fill hotkey failed: {e}")

    listener = _make_listener(_on_capture, _on_fill)
    listener.daemon = True
    listener.start()
    logger.info(f"Hotkeys active — capture: {HOTKEY_CAPTURE}  fill: {HOTKEY_FILL}")
    return listener


def start_polling(interval: int, light_pipeline_fn: Callable) -> threading.Thread:
    """Poll screen every `interval` seconds; call light_pipeline if screen changed."""
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

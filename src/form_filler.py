"""
Suggest-mode form filler.

Two fill modes:
  1. fill_at_cursor() — called by fill hotkey (Ctrl+Shift+F10).
     Looks at where your mouse cursor is RIGHT NOW, finds the nearest detected
     form label, copies the matching value to clipboard, and shows a notification.
     You then press Ctrl+V to paste it in.

  2. fill_pending() — called by tray menu "Fill detected form".
     Iterates ALL detected fields, clicks each one and pastes the value.

Profile values come from [profile] in config.toml.
"""
import time
import math
import pyautogui
import pyperclip
from loguru import logger

from src.form_detector import DetectedForm
from src.config import PROFILE


_pending_form: DetectedForm | None = None
_pending_boxes: list[dict] | None = None


def _notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Omniscient Observer",
            timeout=6,
        )
    except Exception:
        pass


def stage_form(form: DetectedForm, word_boxes: list[dict]) -> None:
    global _pending_form, _pending_boxes
    _pending_form = form
    _pending_boxes = word_boxes
    logger.info(f"Form staged with {len(form.fields)} fields")


def has_pending() -> bool:
    return _pending_form is not None


def fill_at_cursor() -> bool:
    """
    Cursor-mode fill: find the form label nearest to the current mouse position
    and copy its profile value to clipboard. Shows a notification so the user
    knows what was copied and can press Ctrl+V to paste.
    Returns True if a value was copied.
    """
    if not _pending_boxes:
        _notify("Form filler", "No form detected yet. Wait for a detection notification.")
        return False

    # Get current mouse position
    cx, cy = pyautogui.position()

    # Find the closest word box that has a matching profile value
    best_box = None
    best_dist = float("inf")
    for box in _pending_boxes:
        label = box["text"].strip().rstrip(":").lower()
        if not PROFILE.get(label):
            continue
        bx = box["left"] + box["width"] / 2
        by = box["top"] + box["height"] / 2
        dist = math.hypot(bx - cx, by - cy)
        if dist < best_dist:
            best_dist = dist
            best_box = box

    if best_box:
        label = best_box["text"].strip().rstrip(":").lower()
        value = PROFILE[label]
        pyperclip.copy(value)
        _notify(
            f"Copied for '{label}'",
            f'"{value}"\nPress Ctrl+V to paste.',
        )
        logger.info(f"Cursor-fill: copied '{label}' = '{value}' (distance {best_dist:.0f}px)")
        return True

    # Fallback: if nothing near cursor matches, copy the first available value
    for box in _pending_boxes:
        label = box["text"].strip().rstrip(":").lower()
        value = PROFILE.get(label, "")
        if value:
            pyperclip.copy(value)
            _notify(
                f"Copied for '{label}'",
                f'"{value}"\nPress Ctrl+V to paste. Move cursor near a different label and press hotkey again.',
            )
            logger.info(f"Cursor-fill fallback: copied '{label}' = '{value}'")
            return True

    _notify("Form filler", "No matching profile values found for detected fields.")
    return False


def fill_pending() -> bool:
    """
    Batch-mode fill: iterate ALL detected fields, click each one,
    and paste the value. Notifies after completion.
    Returns True if anything was filled.
    """
    global _pending_form, _pending_boxes
    if not _pending_form or not _pending_boxes:
        logger.info("No pending form to fill")
        _notify("Form filler", "No form detected. Trigger a screen capture first.")
        return False

    filled_labels = []
    skipped = []

    for box in _pending_boxes:
        label = box["text"].strip().rstrip(":").lower()
        value = PROFILE.get(label, "")
        if not value:
            continue
        # Click just to the right of the label (estimated input field position)
        click_x = box["left"] + box["width"] + 80
        click_y = box["top"] + box["height"] // 2
        try:
            pyautogui.click(click_x, click_y)
            time.sleep(0.15)
            pyperclip.copy(value)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            filled_labels.append(label)
            logger.info(f"Filled '{label}' at ({click_x},{click_y})")
        except Exception as e:
            skipped.append(label)
            logger.error(f"Fill error on '{label}': {e}")

    _pending_form = None
    _pending_boxes = None

    if filled_labels:
        summary = ", ".join(filled_labels)
        _notify("Form filled", f"Filled: {summary}")
        logger.info(f"Form fill complete — {len(filled_labels)} field(s): {summary}")
    else:
        _notify("Form filler", "No profile values matched the detected fields. Check [profile] in config.toml.")
        logger.warning("Form fill: no fields matched profile")

    return bool(filled_labels)

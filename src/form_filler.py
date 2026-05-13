"""
Suggest-mode form filler.

Fill hotkey (Ctrl+Shift+F10) — cursor-aware cycle mode:
  - Tries to find the form label nearest to your mouse cursor.
  - If word-box coordinates are unavailable (OCR confidence was low), cycles
    through detected fields sequentially — each press copies the next value.
  - Shows a notification: "Copied 'Nagarjun' for 'name' — press Ctrl+V to paste."

Tray "Fill detected form" — batch mode:
  - Iterates all detected fields, clicks the estimated input location, pastes.

Profile values come from [profile] in config.toml.
"""
import math
import time
import pyautogui
import pyperclip
from loguru import logger

from src.form_detector import DetectedForm
from src.config import PROFILE


_pending_form:   DetectedForm | None = None
_pending_boxes:  list[dict] | None   = None
_cycle_index:    int                  = 0   # tracks position in cycle-fill


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
    global _pending_form, _pending_boxes, _cycle_index
    # Only reset the cycle index when the set of detected fields actually changes.
    # Always update word_boxes so cursor-fill never works with stale coordinates.
    old_fields = set(_pending_form.fields) if _pending_form else set()
    new_fields = set(form.fields)
    if old_fields != new_fields:
        _cycle_index = 0
        logger.info(f"Form fields changed: {old_fields} → {new_fields}")
    _pending_form  = form
    _pending_boxes = word_boxes
    boxes_count = len(word_boxes) if word_boxes else 0
    logger.info(f"Form staged: {len(form.fields)} fields, {boxes_count} word boxes")


def has_pending() -> bool:
    return _pending_form is not None


def _fillable_fields() -> list[tuple[str, str]]:
    """Return [(label, value)] for detected fields that have profile values."""
    if not _pending_form:
        return []
    result = []
    for field in _pending_form.fields:
        value = PROFILE.get(field.lower(), "")
        if value:
            result.append((field, value))
    return result


def fill_at_cursor() -> bool:
    """
    Hotkey fill mode. Two strategies tried in order:
    1. Cursor proximity — find the word box nearest to the mouse, copy its value.
    2. Cycle fallback  — if no word boxes available, cycle through fields sequentially.
    """
    global _cycle_index

    if not _pending_form:
        logger.info("fill_at_cursor: no pending form")
        _notify("Form filler", "No form detected yet — wait for a poll or press Ctrl+Shift+F9 to capture.")
        return False

    fillable = _fillable_fields()
    if not fillable:
        detected = ", ".join(_pending_form.fields)
        logger.warning(f"fill_at_cursor: no profile values for detected fields: {detected}")
        _notify(
            "Form filler — no match",
            f"Detected fields: {detected}\n"
            "Add their values to [profile] in config.toml."
        )
        return False

    # --- Strategy 1: cursor proximity via word boxes ---
    if _pending_boxes:
        cx, cy = pyautogui.position()
        best_label, best_value, best_dist = None, None, float("inf")
        for box in _pending_boxes:
            label = box["text"].strip().rstrip(":").lower()
            value = PROFILE.get(label, "")
            if not value:
                continue
            bx = box["left"] + box["width"] / 2
            by = box["top"] + box["height"] / 2
            dist = math.hypot(bx - cx, by - cy)
            if dist < best_dist:
                best_dist, best_label, best_value = dist, label, value

        if best_label:
            pyperclip.copy(best_value)
            _notify(f"Copied for '{best_label}'", f'"{best_value}"\nPress Ctrl+V to paste.')
            logger.info(f"Cursor-fill: '{best_label}' = '{best_value}' (cursor dist {best_dist:.0f}px)")
            return True
        else:
            logger.warning("fill_at_cursor: word boxes present but no cursor-proximity match — falling through to cycle")
    else:
        logger.warning("fill_at_cursor: no word boxes (OCR confidence too low) — using cycle mode")

    # --- Strategy 2: cycle through fillable fields ---
    idx   = _cycle_index % len(fillable)
    label, value = fillable[idx]
    _cycle_index = idx + 1

    pyperclip.copy(value)
    remaining = len(fillable) - (idx + 1)
    hint = f"Press hotkey again for next field ({remaining} more)." if remaining else "All fields cycled — starting over next press."
    _notify(
        f"Copied for '{label}' ({idx + 1}/{len(fillable)})",
        f'"{value}"\nPress Ctrl+V to paste.\n{hint}',
    )
    logger.info(f"Cycle-fill [{idx + 1}/{len(fillable)}]: '{label}' = '{value}'")
    return True


def fill_pending() -> bool:
    """
    Batch fill mode (tray menu). Clicks each detected field location and pastes.
    Shows a summary notification when done.
    """
    global _pending_form, _pending_boxes, _cycle_index

    if not _pending_form or not _pending_boxes:
        logger.info("fill_pending: no pending form or word boxes")
        _notify("Form filler", "No form detected. Trigger a capture first (Ctrl+Shift+F9).")
        return False

    filled_labels = []
    for box in _pending_boxes:
        label = box["text"].strip().rstrip(":").lower()
        value = PROFILE.get(label, "")
        if not value:
            continue
        click_x = box["left"] + box["width"] + 80
        click_y = box["top"] + box["height"] // 2
        try:
            pyautogui.click(click_x, click_y)
            time.sleep(0.15)
            pyperclip.copy(value)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            filled_labels.append(label)
            logger.info(f"Batch-fill: '{label}' at ({click_x},{click_y})")
        except Exception as e:
            logger.error(f"Batch-fill error on '{label}': {e}")

    _pending_form  = None
    _pending_boxes = None
    _cycle_index   = 0

    if filled_labels:
        _notify("Form filled", f"Filled: {', '.join(filled_labels)}")
        logger.info(f"Batch-fill complete — {len(filled_labels)} field(s): {', '.join(filled_labels)}")
    else:
        _notify("Form filler", "No profile values matched the detected fields.")
        logger.warning("Batch-fill: no fields matched profile values")

    return bool(filled_labels)

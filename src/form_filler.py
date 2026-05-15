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
import time
import pyautogui
import pyperclip
from loguru import logger

from src.form_detector import DetectedForm
from src.config import PROFILE


_pending_form:   DetectedForm | None = None
_pending_boxes:  list[dict] | None   = None
_cycle_index:    int                  = 0   # tracks position in cycle-fill

# Common label synonyms → profile key (all lowercase)
_SYNONYMS: dict[str, str] = {
    "mobile":       "phone",
    "cell":         "phone",
    "telephone":    "phone",
    "tel":          "phone",
    "phone number": "phone",
    "mobile number":"phone",
    "e-mail":       "email",
    "dob":          "date of birth",
    "surname":      "last name",
    "family name":  "last name",
    "given name":   "first name",
    "full name":    "name",
    "user name":    "username",
    "user":         "username",
    "zip":          "zip",
    "postal":       "zip",
    "postal code":  "zip",
    "pin":          "zip",
    "pincode":      "zip",
}


def _notify(title: str, message: str = "", level: str = "info") -> None:
    """Push a toast via the in-app overlay (falls back to plyer if tkinter fails)."""
    from src import overlay
    overlay.push(title, message, level=level)


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


def _profile_value(label: str) -> str:
    """Look up a form field label in PROFILE with synonym resolution."""
    key = label.lower()
    if PROFILE.get(key):
        return PROFILE[key]
    resolved = _SYNONYMS.get(key, "")
    return PROFILE.get(resolved, "") if resolved else ""


def _fillable_fields() -> list[tuple[str, str]]:
    """Return [(label, value)] for detected fields that have profile values."""
    if not _pending_form:
        return []
    result = []
    for field in _pending_form.fields:
        value = _profile_value(field)
        if value:
            result.append((field, value))
    return result


_STOP_WORDS = frozenset({"of", "the", "and", "or", "in", "at", "a", "an", "to", "for"})


def _field_screen_positions() -> list[tuple[str, str, float, float, float, float]]:
    """
    Return [(field_label, value, center_x, center_y, top_y, bottom_y)] for fillable fields.
    Locates each multi-word field label on screen by finding word boxes whose
    text is a meaningful (non-stop) word of the field name.
    Stop words like 'of' are excluded to avoid false matches.
    top_y / bottom_y give the vertical extent of the label so the cursor
    matcher can detect when the cursor is on the same row as a label
    (e.g. cursor in an input box to the right of the label).
    """
    if not _pending_form or not _pending_boxes:
        return []
    positions = []
    for field in _pending_form.fields:
        value = _profile_value(field)
        if not value:
            continue
        all_words  = set(field.lower().split())
        key_words  = all_words - _STOP_WORDS or all_words
        matching = [
            b for b in _pending_boxes
            if b["text"].strip().rstrip(":.,").lower() in key_words
        ]
        if not matching:
            continue
        cx = sum(b["left"] + b["width"] / 2 for b in matching) / len(matching)
        cy = sum(b["top"] + b["height"] / 2 for b in matching) / len(matching)
        top_y    = min(b["top"] for b in matching)
        bottom_y = max(b["top"] + b["height"] for b in matching)
        positions.append((field, value, cx, cy, top_y, bottom_y))
    return positions


# Row matching: forms are arranged label-then-input on the same horizontal row,
# and the cursor sits inside the input box (well to the right of the label
# center). Euclidean distance picks wrong fields when two rows are close.
# Score below is biased toward matching by row first, then by X proximity.
_Y_WEIGHT   = 6.0    # vertical mismatch costs 6× as much as horizontal
_ROW_PAD    = 65     # px below label bottom counted as "same row" — 65px covers Google Forms
                     # where the label sits above the input (not beside it)
_MAX_SCORE  = 800    # if best score exceeds this, cursor is nowhere near any field — fall to cycle mode


def _row_score(cx: float, cy: float, pos: tuple[str, str, float, float, float, float]) -> float:
    """
    Distance score combining row alignment and horizontal proximity.
    Lower = better. Cursor on same row as label → only X distance counts.
    """
    fx       = pos[2]
    top_y    = pos[4]
    bottom_y = pos[5]
    if (top_y - _ROW_PAD) <= cy <= (bottom_y + _ROW_PAD):
        return abs(cx - fx)
    y_dist = min(abs(cy - top_y), abs(cy - bottom_y))
    return y_dist * _Y_WEIGHT + abs(cx - fx)


def fill_at_cursor() -> bool:
    """
    Hotkey fill mode. Two strategies tried in order:
    1. Cursor proximity — find the detected field label nearest to mouse cursor.
       Uses field-level positions (handles multi-word labels and synonyms).
    2. Cycle fallback  — if no position data, cycle through fields sequentially.
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

    # --- Strategy 1: cursor proximity via row-weighted scoring ---
    # Forms are arranged label-then-input on one row. Cursor sits in the input
    # box well to the right of the label center, so euclidean distance picks
    # wrong fields. _row_score: same row → only X distance; different row →
    # vertical distance dominates.
    field_positions = _field_screen_positions()
    if field_positions:
        cx, cy = pyautogui.position()
        best_label, best_value, best_score = None, None, float("inf")
        for pos in field_positions:
            score = _row_score(cx, cy, pos)
            if score < best_score:
                best_score, best_label, best_value = score, pos[0], pos[1]

        if best_label and best_score <= _MAX_SCORE:
            pyperclip.copy(best_value)
            _notify(
                f"Copied — '{best_label}'",
                f'Value: "{best_value}"\n→ Click the field, then press Ctrl+V to paste.\nPress F10 again for the next field.',
                level="success",
            )
            logger.info(f"Cursor-fill: '{best_label}' = '{best_value}' (row score {best_score:.0f})")
            return True
        elif best_label:
            logger.warning(f"fill_at_cursor: best score {best_score:.0f} > {_MAX_SCORE} — cursor not near any field, falling to cycle")
        else:
            logger.warning("fill_at_cursor: field positions computed but no match — falling through to cycle")
    else:
        logger.warning("fill_at_cursor: no field positions (word boxes empty or no matches) — using cycle mode")

    # --- Strategy 2: cycle through fillable fields ---
    idx   = _cycle_index % len(fillable)
    label, value = fillable[idx]
    _cycle_index = idx + 1

    pyperclip.copy(value)
    remaining = len(fillable) - (idx + 1)
    hint = f"Press F10 again for next field ({remaining} more)." if remaining else "All fields done — next press restarts from the top."
    _notify(
        f"Copied [{idx + 1}/{len(fillable)}] — '{label}'",
        f'Value: "{value}"\n→ Click the field, then Ctrl+V to paste.\n{hint}',
        level="success",
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
        value = _profile_value(label)
        if not value:
            continue
        click_x = box["left"] + box["width"] + 80
        click_y = box["top"] + box["height"] // 2
        try:
            pyautogui.click(click_x, click_y)
            time.sleep(0.40)          # wait for the field to actually focus
            pyperclip.copy(value)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.25)          # wait for paste to land before moving to next field
            filled_labels.append(label)
            logger.info(f"Batch-fill: '{label}' at ({click_x},{click_y})")
            time.sleep(0.15)          # brief gap between fields
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

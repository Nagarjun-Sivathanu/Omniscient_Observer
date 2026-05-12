"""
Suggest-mode form filler.
Stores the last detected form. When the user confirms (via tray or fill hotkey),
uses pyautogui + OCR word boxes to click each field and type the value.
"""
import time
import pyautogui
import pyperclip
from loguru import logger

from src.form_detector import DetectedForm

# User profile — update config.toml or extend this in future versions
PROFILE: dict[str, str] = {
    "name":       "",
    "first name": "",
    "last name":  "",
    "email":      "",
    "phone":      "",
    "address":    "",
    "city":       "",
    "zip":        "",
    "country":    "",
}

_pending_form: DetectedForm | None = None
_pending_boxes: list[dict] | None = None


def stage_form(form: DetectedForm, word_boxes: list[dict]) -> None:
    """Store a detected form for later confirmation."""
    global _pending_form, _pending_boxes
    _pending_form = form
    _pending_boxes = word_boxes
    logger.info(f"Form staged with {len(form.fields)} fields")


def has_pending() -> bool:
    return _pending_form is not None


def fill_pending() -> bool:
    """
    Fill the staged form. Returns True if anything was filled.
    Matches OCR word positions to profile keys and types values.
    """
    global _pending_form, _pending_boxes
    if not _pending_form or not _pending_boxes:
        logger.info("No pending form to fill")
        return False

    filled = 0
    for box in _pending_boxes:
        label = box["text"].strip().rstrip(":").lower()
        value = PROFILE.get(label, "")
        if not value:
            continue
        # Click just to the right of the label (estimated input field location)
        click_x = box["left"] + box["width"] + 80
        click_y = box["top"] + box["height"] // 2
        try:
            pyautogui.click(click_x, click_y)
            time.sleep(0.1)
            pyperclip.copy(value)
            pyautogui.hotkey("ctrl", "v")
            filled += 1
            logger.info(f"Filled '{label}' at ({click_x},{click_y})")
        except Exception as e:
            logger.error(f"Fill error on '{label}': {e}")

    _pending_form = None
    _pending_boxes = None
    logger.info(f"Form fill complete — {filled} fields filled")
    return filled > 0


def load_profile_from_config(profile_dict: dict) -> None:
    """Update the in-memory profile from a dict (e.g. loaded from config)."""
    PROFILE.update({k.lower(): v for k, v in profile_dict.items()})

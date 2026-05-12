"""Detect fillable forms on screen using OCR heuristics + Moondream confirmation."""
import re
from dataclasses import dataclass, field
from PIL import Image
from loguru import logger

from src import ocr, llm

_FIELD_PATTERNS = re.compile(
    r"\b(name|first name|last name|email|e-mail|phone|mobile|address|city|zip|"
    r"postal|country|password|username|user name|date of birth|dob|"
    r"card number|cvv|expiry|submit|sign up|sign in|register|login)\b",
    re.IGNORECASE,
)
_MIN_FIELD_HITS = 2   # need at least this many distinct form keywords


@dataclass
class DetectedForm:
    fields: list[str] = field(default_factory=list)   # OCR-detected field labels
    confirmed_by_vision: bool = False
    raw_ocr: str = ""


def detect(img: Image.Image, use_vision: bool = True) -> DetectedForm | None:
    """
    Run form detection on a screenshot.
    Returns DetectedForm if a form is found, None otherwise.
    use_vision=True calls Moondream for a second confirmation pass.
    """
    text = ocr.extract_text(img)
    hits = _FIELD_PATTERNS.findall(text)
    unique_hits = list({h.lower() for h in hits})

    if len(unique_hits) < _MIN_FIELD_HITS:
        return None

    logger.info(f"Form heuristic matched: {unique_hits}")
    form = DetectedForm(fields=unique_hits, raw_ocr=text)

    if use_vision:
        answer = llm.analyze_screenshot(
            img,
            "Is there a fillable form or input fields visible in this screenshot? "
            "Reply with only YES or NO."
        )
        form.confirmed_by_vision = answer.strip().upper().startswith("Y")
        logger.info(f"Vision form confirmation: {form.confirmed_by_vision}")
        if not form.confirmed_by_vision:
            return None

    return form

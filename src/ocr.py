"""Tesseract OCR wrapper with image preprocessing."""
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from loguru import logger

from src.config import TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def _preprocess(img: Image.Image) -> Image.Image:
    """Grayscale + mild sharpening improves Tesseract accuracy on UI text."""
    gray = img.convert("L")
    sharp = ImageEnhance.Sharpness(gray).enhance(2.0)
    return sharp


def extract_text(img: Image.Image) -> str:
    """Return raw OCR text from a PIL screenshot image."""
    try:
        processed = _preprocess(img)
        text = pytesseract.image_to_string(processed, config="--psm 6")
        return text.strip()
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return ""


def extract_words_with_boxes(img: Image.Image) -> list[dict]:
    """Return list of {text, left, top, width, height} for each word detected."""
    try:
        processed = _preprocess(img)
        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)
        words = []
        for i, word in enumerate(data["text"]):
            if word.strip() and int(data["conf"][i]) > 40:
                words.append({
                    "text": word,
                    "left":   data["left"][i],
                    "top":    data["top"][i],
                    "width":  data["width"][i],
                    "height": data["height"][i],
                })
        return words
    except Exception as e:
        logger.error(f"OCR word extraction failed: {e}")
        return []

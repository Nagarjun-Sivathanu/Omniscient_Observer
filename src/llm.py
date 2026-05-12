"""Ollama API client — text generation, vision, and embeddings."""
import base64
from io import BytesIO
import httpx
from PIL import Image
from loguru import logger

from src.config import OLLAMA_BASE, LLM_MODEL, VISION_MODEL, EMBED_MODEL

_TIMEOUT_LLM   = 120
_TIMEOUT_VISION = 90
_TIMEOUT_EMBED  = 90   # nomic-embed-text cold-start can take ~60s on first call


def _post(endpoint: str, payload: dict, timeout: int) -> dict:
    url = f"{OLLAMA_BASE}{endpoint}"
    r = httpx.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def generate(prompt: str, system: str = "", model: str = LLM_MODEL) -> str:
    """Call LLM for text generation. Model unloads after use (keep_alive=0)."""
    payload = {
        "model":      model,
        "prompt":     prompt,
        "stream":     False,
        "keep_alive": "0",
    }
    if system:
        payload["system"] = system
    try:
        data = _post("/api/generate", payload, _TIMEOUT_LLM)
        return data["response"].strip()
    except Exception as e:
        logger.error(f"LLM generate failed: {e}")
        return ""


def embed(text: str) -> list[float]:
    """Embed text with nomic-embed-text. Model stays resident (keep_alive=-1)."""
    try:
        # Ollama ≥0.2 uses /api/embed with "input" key; returns {"embeddings": [[...]]}
        data = _post("/api/embed", {
            "model": EMBED_MODEL,
            "input": text[:4000],
        }, _TIMEOUT_EMBED)
        return data["embeddings"][0]
    except Exception as e:
        logger.error(f"Embed failed: {e}")
        return []


def _pil_to_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def analyze_screenshot(img: Image.Image, prompt: str) -> str:
    """Send screenshot to Moondream2 for visual analysis. Model unloads after use."""
    try:
        data = _post("/api/generate", {
            "model":      VISION_MODEL,
            "prompt":     prompt,
            "images":     [_pil_to_b64(img)],
            "stream":     False,
            "keep_alive": "0",
        }, _TIMEOUT_VISION)
        return data["response"].strip()
    except Exception as e:
        logger.error(f"Vision analyze failed: {e}")
        return ""


def summarize_as_note(text: str, window_title: str = "") -> str:
    """Ask LLM to summarize screen content into a concise Obsidian-ready note."""
    context = f"Active window: {window_title}\n\n" if window_title else ""
    prompt = (
        f"{context}Screen text:\n{text[:3000]}\n\n"
        "Write a concise, factual note summarizing the key information from this screen. "
        "Use markdown. Start with a ## heading. Max 200 words."
    )
    return generate(prompt)


def classify_activity(window_title: str, ocr_text: str) -> str:
    """Return a short activity label, e.g. 'Watching YouTube', 'Reading docs'."""
    prompt = (
        f"Window: {window_title}\nText sample: {ocr_text[:500]}\n\n"
        "In 3-5 words, classify what the user is doing (e.g. 'Watching a YouTube video', "
        "'Writing code', 'Reading an article', 'Filling a web form'). Reply with only the label."
    )
    return generate(prompt)


def extract_calendar_events(text: str) -> list[dict]:
    """Extract calendar events from text. Returns list of {title, date, time, description}."""
    prompt = (
        f"Text:\n{text[:2000]}\n\n"
        "Find any events, meetings, deadlines, or appointments mentioned. "
        "Reply as a JSON array of objects with keys: title, date (YYYY-MM-DD or empty), "
        "time (HH:MM or empty), description. "
        "If nothing found, reply with an empty JSON array []."
    )
    raw = generate(prompt)
    import json, re
    try:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return []

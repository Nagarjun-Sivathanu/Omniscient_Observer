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


def summarize_as_note(text: str, window_title: str = "", related_notes: str = "") -> tuple[str, str]:
    """
    Ask LLM to produce a structured Obsidian note from screen content.
    Returns (title, body_markdown).
    title is a short, file-safe name for the note.
    body_markdown is the full note content.
    """
    context_parts = []
    if window_title:
        context_parts.append(f"Active window: {window_title}")
    if related_notes:
        context_parts.append(f"Related past notes:\n{related_notes}")
    context_parts.append(f"Screen text:\n{text[:4000]}")
    full_context = "\n\n".join(context_parts)

    system = (
        "You are a personal knowledge assistant. Your job is to convert raw screen text "
        "into a clean, structured Obsidian markdown note. Be factual and concise. "
        "Do NOT invent information not present in the screen text."
    )
    prompt = (
        f"{full_context}\n\n"
        "Write a structured Obsidian note. Follow this format exactly:\n\n"
        "TITLE: <short descriptive title, 3-7 words, no special characters>\n\n"
        "## Summary\n"
        "<2-4 sentence summary of what is on screen>\n\n"
        "## Key Points\n"
        "- <bullet point 1>\n"
        "- <bullet point 2>\n"
        "...\n\n"
        "## Details\n"
        "<any important details, steps, code snippets, or data worth preserving>\n\n"
        "Only include sections that have real content. "
        "If there is highlighted or emphasized text on screen, quote it under a '## Highlights' section."
    )
    raw = generate(prompt, system=system)
    if not raw:
        return "", ""

    # Split title from body
    lines = raw.strip().splitlines()
    title = ""
    body_lines = []
    for i, line in enumerate(lines):
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
            body_lines = lines[i + 1:]
            break
    else:
        body_lines = lines

    if not title:
        # Fallback: grab the first heading or first non-empty line
        for line in body_lines:
            stripped = line.lstrip("#").strip()
            if stripped:
                title = stripped[:60]
                break

    body = "\n".join(body_lines).strip()
    return title, body


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

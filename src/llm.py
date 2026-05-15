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


def generate(prompt: str, system: str = "", model: str = LLM_MODEL, temperature: float = 0.2) -> str:
    """Call LLM for text generation. Model unloads after use (keep_alive=0)."""
    payload = {
        "model":      model,
        "prompt":     prompt,
        "stream":     False,
        "keep_alive": "0",
        "options":    {"temperature": temperature},
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
    Produce a structured Obsidian note from OCR screen text.
    related_notes is accepted for API compatibility but NOT fed to the LLM
    (small models hallucinate when given extra context they didn't see).
    Returns (title, body_markdown).
    """
    header = f"Window: {window_title}\n\n" if window_title else ""

    system = (
        "You are a personal note-taker. Write clean, human-readable notes. "
        "STRICT RULES — break any of these and the note is useless:\n"
        "1. Write ONLY facts present in the text. Never add, guess, or infer anything.\n"
        "2. NEVER mention OCR, scanning, screen capture, transcription, or any software.\n"
        "3. NEVER say 'the text provides', 'the OCR text', 'based on the screen', 'it appears', "
        "'it seems', 'I cannot see', or any similar meta-commentary.\n"
        "4. Write as if you personally read the page and are taking notes on it.\n"
        "5. If the content is sparse, write a short note — never pad it out.\n"
        "6. Omit any section that has nothing real to fill."
    )

    prompt = (
        f"{header}"
        f"Page content:\n---\n{text[:3500]}\n---\n\n"
        "Write a note on the above content. Format:\n\n"
        "TITLE: <3-6 words that name the actual topic, no punctuation>\n\n"
        "## Summary\n"
        "<1-3 sentences on what this page is actually about>\n\n"
        "## Key Points\n"
        "- <actual facts, names, numbers, or items from the content>\n\n"
        "Only add a ## Details section if there is specific structured data "
        "(dates, lists, steps, codes, prices) worth preserving verbatim."
    )

    raw = generate(prompt, system=system, temperature=0.1)
    if not raw:
        return "", ""

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
    """
    Extract calendar events from OCR text. Returns [{title, date, time, description}].
    Feeds today's date into the prompt so the LLM can resolve relative references
    like "tomorrow", "next Monday", "this Friday" into real YYYY-MM-DD values.
    """
    from datetime import date as _date
    today_iso   = _date.today().isoformat()                          # 2026-05-15
    today_named = _date.today().strftime("%A, %d %B %Y")            # Thursday, 15 May 2026

    system = (
        "You are a calendar extraction assistant. "
        f"Today is {today_named} (ISO: {today_iso}). "
        "Your sole job is to extract events, appointments, meetings, exams, deadlines, "
        "and any other scheduled items from the provided screen text. "
        "Rules you MUST follow:\n"
        "1. Resolve ALL relative dates (today, tomorrow, next Monday, this Friday, next week) "
        "to absolute YYYY-MM-DD using today's date above.\n"
        "2. Never invent events. Only extract what is explicitly stated in the text.\n"
        "3. Reply with ONLY a valid JSON array — no explanation, no markdown fences.\n"
        "4. If no events are found, reply with exactly: []"
    )

    prompt = (
        f"Screen text:\n{text[:4000]}\n\n"
        "Extract every event from the text. For each one output a JSON object with these fields:\n"
        '  "title": short name of the event (max 10 words)\n'
        '  "date": YYYY-MM-DD — resolve relative dates using today; empty string if truly unknown\n'
        '  "time": HH:MM in 24-hour format, or empty string if not mentioned\n'
        '  "description": any extra context — venue, duration, who it is with (empty string if none)\n\n'
        "Reply ONLY with the JSON array."
    )

    raw = generate(prompt, system=system, temperature=0.05)
    import json, re
    try:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return []

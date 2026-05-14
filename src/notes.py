"""Write structured notes to an Obsidian vault as markdown files."""
import re
from datetime import datetime
from pathlib import Path
from loguru import logger

from src.config import OBSIDIAN_VAULT


def _vault() -> Path | None:
    if not OBSIDIAN_VAULT:
        logger.warning("Obsidian vault path not set in config.toml — skipping note write")
        return None
    p = Path(OBSIDIAN_VAULT)
    if not p.exists():
        logger.warning(f"Obsidian vault not found: {p}")
        return None
    return p


def _safe_filename(title: str) -> str:
    """Convert a title string into a valid Windows/Obsidian filename."""
    # Remove characters that are invalid in Windows filenames
    safe = re.sub(r'[\\/*?:"<>|]', "", title)
    safe = safe.strip().strip(".")
    safe = safe[:80]  # cap length
    return safe or "Observer Note"



def write_note(
    title: str,
    body: str,
    source_app: str = "",
    tags: list[str] | None = None,
    related_titles: list[str] | None = None,
) -> Path | None:
    """
    Write a markdown note to the Obsidian vault.
    - title: content-based name (becomes the filename)
    - body: the note body markdown
    - related_titles: list of past note titles to link as [[wikilinks]]
    Returns the file path or None.
    """
    vault = _vault()
    if vault is None:
        return None

    tags = tags or ["omniscient-observer"]
    now = datetime.now()

    # Build filename from content title + timestamp disambiguator
    safe_title = _safe_filename(title) if title else ""
    ts_suffix = now.strftime("%Y-%m-%d %H-%M")
    filename = f"{safe_title} {ts_suffix}.md" if safe_title else f"Observer {ts_suffix}.md"

    tag_str = "\n".join(f"  - {t}" for t in tags)
    frontmatter = (
        f"---\n"
        f"created: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"source: {source_app or 'screen'}\n"
        f"tags:\n{tag_str}\n"
        f"---\n\n"
    )

    # Build related-links block
    links_block = ""
    if related_titles:
        link_lines = "\n".join(f"- [[{t}]]" for t in related_titles)
        links_block = f"\n\n## Related\n{link_lines}"

    full_content = frontmatter + body + links_block

    folder = vault / "Omniscient Observer"
    folder.mkdir(exist_ok=True)
    note_path = folder / filename
    note_path.write_text(full_content, encoding="utf-8")
    logger.info(f"Note written: {note_path.name}")
    return note_path


def list_notes_today() -> list[dict]:
    """Return today's notes from the vault as [{name, path, created_iso}], newest first."""
    vault = _vault()
    if vault is None:
        return []
    folder = vault / "Omniscient Observer"
    if not folder.exists():
        return []
    today = datetime.now().date()
    rows = []
    for f in folder.glob("*.md"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
        except OSError:
            continue
        if mtime.date() != today:
            continue
        rows.append({
            "name":        f.stem,
            "path":        str(f),
            "created_iso": mtime.isoformat(timespec="seconds"),
        })
    rows.sort(key=lambda r: r["created_iso"], reverse=True)
    return rows

"""Write structured notes to an Obsidian vault as markdown files."""
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


def write_note(content: str, source_app: str = "", tags: list[str] | None = None) -> Path | None:
    """Write a markdown note to the Obsidian vault. Returns the file path or None."""
    vault = _vault()
    if vault is None:
        return None

    tags = tags or ["omniscient-observer"]
    now = datetime.now()
    filename = now.strftime("Observer %Y-%m-%d %H-%M-%S.md")
    tag_str = "\n".join(f"  - {t}" for t in tags)

    frontmatter = (
        f"---\n"
        f"created: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"source: {source_app or 'screen'}\n"
        f"tags:\n{tag_str}\n"
        f"---\n\n"
    )

    folder = vault / "Omniscient Observer"
    folder.mkdir(exist_ok=True)
    note_path = folder / filename
    note_path.write_text(frontmatter + content, encoding="utf-8")
    logger.info(f"Note written: {note_path.name}")
    return note_path

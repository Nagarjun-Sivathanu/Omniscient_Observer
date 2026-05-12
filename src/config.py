import toml
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_cfg = toml.load(_ROOT / "config.toml")

# paths
TESSERACT_CMD   = _cfg["paths"]["tesseract"]
OBSIDIAN_VAULT  = _cfg["paths"]["obsidian_vault"].strip()

# hotkeys
HOTKEY_CAPTURE  = _cfg["hotkeys"]["capture"]
HOTKEY_FILL     = _cfg["hotkeys"]["fill"]

# ollama
OLLAMA_BASE     = _cfg["ollama"]["base_url"]
LLM_MODEL       = _cfg["ollama"]["llm_model"]
VISION_MODEL    = _cfg["ollama"]["vision_model"]
EMBED_MODEL     = _cfg["ollama"]["embed_model"]

# capture
POLL_INTERVAL   = int(_cfg["capture"]["poll_interval"])
CHANGE_THRESH   = float(_cfg["capture"]["change_threshold"])

# activity
ALERT_MINUTES   = int(_cfg["activity"]["alert_threshold_minutes"])

# memory
DB_PATH         = _ROOT / _cfg["memory"]["db_path"]
CHROMA_PATH     = str(_ROOT / _cfg["memory"]["chroma_path"])
MAX_RECALL      = int(_cfg["memory"]["max_recall"])
PRUNE_DAYS      = int(_cfg["memory"]["prune_after_days"])

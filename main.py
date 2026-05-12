"""
Omniscient Observer — entry point.

Run:
    python main.py

Hotkeys:
    Ctrl+Shift+Space  → full AI pipeline (capture → summarise → Obsidian)
    Ctrl+Shift+F      → fill the last detected form

Tray icon:
    Right-click → Pause / Fill form / Quit
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from src.config import POLL_INTERVAL
from src import capture, pipeline, form_filler
from src.activity import ActivityMonitor
from src.tray import build_tray
from src.pipeline import _notify


def _setup_logging() -> None:
    log_path = Path(__file__).parent / "logs" / "observer.log"
    log_path.parent.mkdir(exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
    logger.add(log_path, level="DEBUG", rotation="10 MB", retention="7 days",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")


def _on_activity_alert(title: str, minutes: float) -> None:
    _notify(
        "Activity reminder",
        f"You have been on '{title}' for {minutes:.0f} minutes.",
    )


def main() -> None:
    _setup_logging()
    logger.info("Omniscient Observer starting…")

    # Activity monitor
    activity = ActivityMonitor(alert_callback=_on_activity_alert)
    activity.start()
    pipeline.set_activity_monitor(activity)

    # Wire fill hotkey to form filler
    def _fill():
        form_filler.fill_pending()

    # Start hotkey listener (background thread)
    capture.start_hotkey_listener(
        full_pipeline_fn=lambda img: pipeline.run_full(img),
        fill_fn=_fill,
    )

    # Start polling loop (background thread)
    capture.start_polling(
        interval=POLL_INTERVAL,
        light_pipeline_fn=lambda img: pipeline.run_light(img),
    )

    logger.info("All systems running. Ctrl+Shift+Space to capture. Right-click tray to quit.")
    _notify("Omniscient Observer", "Running. Press Ctrl+Shift+Space to capture screen.")

    # System tray runs on main thread (required by pystray on Windows)
    tray = build_tray()
    tray.run()

    logger.info("Observer stopped.")


if __name__ == "__main__":
    main()

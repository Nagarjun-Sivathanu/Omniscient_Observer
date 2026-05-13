"""
Omniscient Observer — entry point.

Run:
    python main.py

Hotkeys:
    Ctrl+Alt+Shift+O  → full AI pipeline (capture → summarise → Obsidian)
    Ctrl+Alt+Shift+F  → fill the last detected form

Tray icon:
    Right-click → Pause / Fill form / Quit
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from src.config import POLL_INTERVAL, HOTKEY_CALENDAR
from src import capture, pipeline, form_filler, llm, memory
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
    label = llm.classify_activity(title, "")
    message = f"You have been on '{title}' for {minutes:.0f} minutes."
    if label:
        message = f"{label} — {minutes:.0f} minutes on '{title}'."
    _notify("Activity reminder", message)


# Global reference to keep listener alive
_hotkey_listener = None


def main() -> None:
    global _hotkey_listener
    _setup_logging()
    logger.info("Omniscient Observer starting…")

    # Activity monitor
    activity = ActivityMonitor(alert_callback=_on_activity_alert)
    activity.start()
    pipeline.set_activity_monitor(activity)
    logger.info("Activity monitor started")

    # Prune old memory on startup to keep the SQLite store clean
    pruned = memory.prune_old_observations()
    if pruned:
        logger.info(f"Pruned {pruned} old observations from memory")

    # Fill hotkey = cursor-mode (copies value for the field your mouse is near)
    # Tray "Fill detected form" = batch-mode (fills all fields automatically)
    def _fill():
        logger.info("Fill hotkey triggered")
        form_filler.fill_at_cursor()

    # Start hotkey listener (background thread)
    logger.info("Starting hotkey listener...")
    _hotkey_listener = capture.start_hotkey_listener(
        full_pipeline_fn=lambda img: pipeline.run_full(img),
        fill_fn=_fill,
        calendar_fn=pipeline.commit_calendar,
    )
    logger.info("Hotkey listener started")

    # Start polling loop (background thread)
    logger.info("Starting polling loop...")
    capture.start_polling(
        interval=POLL_INTERVAL,
        light_pipeline_fn=lambda img: pipeline.run_light(img),
    )
    logger.info("Polling loop started")

    logger.info(
        "All systems running. "
        "Ctrl+Shift+F9=capture  Ctrl+Shift+F10=fill(cursor)  Ctrl+Shift+F11=commit calendar. "
        "Right-click tray to quit."
    )
    _notify(
        "Omniscient Observer running",
        "Ctrl+Shift+F9 = capture screen\n"
        "Ctrl+Shift+F10 = fill field at cursor\n"
        "Ctrl+Shift+F11 = commit calendar events",
    )

    # System tray runs on main thread (required by pystray on Windows)
    logger.info("Building system tray...")
    tray = build_tray()
    logger.info("System tray built, starting...")
    tray.run()

    logger.info("Observer stopped.")


if __name__ == "__main__":
    main()

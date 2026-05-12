"""System tray icon and menu using pystray + PIL."""
from PIL import Image, ImageDraw, ImageFont
import pystray
from loguru import logger

from src import capture, form_filler


def _make_icon() -> Image.Image:
    """Draw a simple 64×64 icon — dark background, white 'O'."""
    img = Image.new("RGBA", (64, 64), color=(30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    # Outer circle
    draw.ellipse([4, 4, 60, 60], outline=(100, 200, 255, 255), width=4)
    # Inner dot
    draw.ellipse([24, 24, 40, 40], fill=(100, 200, 255, 255))
    return img


def _on_pause(icon, item):
    paused = not capture.is_paused()
    capture.set_paused(paused)
    icon.update_menu()
    logger.info(f"Observer {'paused' if paused else 'resumed'} from tray")


def _on_fill(icon, item):
    if form_filler.has_pending():
        logger.info("Tray: filling pending form")
        form_filler.fill_pending()
    else:
        logger.info("Tray: no pending form")


def _on_quit(icon, item):
    logger.info("Quit requested from tray")
    icon.stop()


def _pause_label(item):
    return "Resume observer" if capture.is_paused() else "Pause observer"


def _fill_label(item):
    return "Fill detected form" + (" ✓ pending" if form_filler.has_pending() else " (none)")


def build_tray() -> pystray.Icon:
    menu = pystray.Menu(
        pystray.MenuItem(_pause_label, _on_pause),
        pystray.MenuItem(_fill_label,  _on_fill),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _on_quit),
    )
    icon = pystray.Icon(
        name="omniscient-observer",
        icon=_make_icon(),
        title="Omniscient Observer",
        menu=menu,
    )
    return icon

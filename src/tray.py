"""System tray icon and menu using pystray + PIL."""
from PIL import Image, ImageDraw
import pystray
from loguru import logger

from src import capture, form_filler, calendar_writer, memory
from src import pipeline as _pipeline


def _make_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), color=(30, 30, 30, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], outline=(100, 200, 255, 255), width=4)
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


def _on_calendar_commit(icon, item):
    logger.info("Tray: committing calendar events")
    _pipeline.commit_calendar()
    icon.update_menu()


def _on_calendar_discard(icon, item):
    logger.info("Tray: discarding calendar events")
    _pipeline.discard_calendar()
    icon.update_menu()


def _on_quit(icon, item):
    logger.info("Quit requested from tray")
    icon.stop()


def _pause_label(item):
    return "Resume observer" if capture.is_paused() else "Pause observer"


def _fill_label(item):
    return "Fill detected form" + (" ✓ pending" if form_filler.has_pending() else " (none)")


def _calendar_commit_label(item):
    n = len(calendar_writer._pending_events)
    return f"Commit {n} calendar event(s)" if n else "Commit calendar events (none)"


def _activity_label(item):
    title, minutes = _pipeline.current_activity()
    if not title:
        return "Activity: nothing tracked yet"
    short = title[:40] + "…" if len(title) > 40 else title
    return f"Now: {short} ({minutes:.0f} min)"


def _fmt_minutes(seconds: float) -> str:
    m = seconds / 60
    if m < 60:
        return f"{m:.0f}m"
    return f"{m / 60:.1f}h"


def _today_total_label(item):
    """Total time across all categories today."""
    totals = memory.daily_category_totals()
    if not totals:
        return "Today: no activity yet"
    total = sum(totals.values())
    return f"Today: {_fmt_minutes(total)} total"


def _today_categories_label(item):
    """Per-category breakdown for today, e.g. 'productive 1.2h · media 25m'."""
    totals = memory.daily_category_totals()
    if not totals:
        return "  (no data yet — check back in 5 min)"
    ordered = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    parts = [f"{cat} {_fmt_minutes(sec)}" for cat, sec in ordered if sec > 0]
    return "  " + " · ".join(parts[:5])


def _top_apps_label(item):
    """Top 3 apps today by time spent."""
    rows = memory.daily_activity_summary()
    if not rows:
        return "  (no app data yet)"
    parts = [
        f"{(r['title'] or r['app_key'])[:25]} {_fmt_minutes(r['total_seconds'])}"
        for r in rows[:3]
    ]
    return "  Top: " + " · ".join(parts)


def build_tray() -> pystray.Icon:
    menu = pystray.Menu(
        pystray.MenuItem(_activity_label,           None, enabled=False),
        pystray.MenuItem(_today_total_label,        None, enabled=False),
        pystray.MenuItem(_today_categories_label,   None, enabled=False),
        pystray.MenuItem(_top_apps_label,           None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_pause_label, _on_pause),
        pystray.MenuItem(_fill_label, _on_fill),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(_calendar_commit_label, _on_calendar_commit),
        pystray.MenuItem("Discard pending calendar events", _on_calendar_discard),
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

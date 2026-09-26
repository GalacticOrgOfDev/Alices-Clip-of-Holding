"""System-tray icon so the bag can live in the background after install."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def build_tray_icon() -> object:
    """Create a small bag-shaped icon at runtime so install needs no assets.

    Returns:
        A Pillow ``Image`` suitable for ``pystray.Icon``.
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 22, 54, 56), radius=8, fill=(36, 28, 58, 255))
    draw.rectangle((22, 14, 42, 26), fill=(92, 64, 160, 255))
    draw.ellipse((28, 10, 36, 18), outline=(230, 210, 120, 255), width=2)
    return image


def start_tray(
    on_open: Callable[[], None],
    on_quit: Callable[[], None],
    icon_path: Path | None = None,
) -> object:
    """Start the tray icon on a daemon thread.

    Args:
        on_open: Open the picker.
        on_quit: Shut the application down.
        icon_path: Optional PNG to use instead of the generated bag.

    Returns:
        The ``pystray.Icon`` instance.

    Raises:
        RuntimeError: If ``pystray`` cannot start.
    """
    import threading

    import pystray
    from PIL import Image

    image: Image.Image
    if icon_path is not None and icon_path.is_file():
        image = Image.open(icon_path)
    else:
        image = build_tray_icon()

    menu = pystray.Menu(
        pystray.MenuItem("Open bag (Ctrl+V)", lambda: on_open(), default=True),
        pystray.MenuItem("Quit", lambda: on_quit()),
    )
    icon = pystray.Icon("alices_clip_of_holding", image, "Alice's Clip of Holding", menu)

    thread = threading.Thread(target=icon.run, name="alice-tray", daemon=True)
    thread.start()
    return icon

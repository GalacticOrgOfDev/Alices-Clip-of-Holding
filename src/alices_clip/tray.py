"""System-tray icon so the bag can live in the background after install."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def build_tray_icon() -> object:
    """Create a small bag-shaped icon at runtime so install needs no assets."""
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
    on_settings: Callable[[], None] | None = None,
    on_open_folder: Callable[[], None] | None = None,
    on_toggle_pause: Callable[[], None] | None = None,
    on_clear_bag: Callable[[], None] | None = None,
    paused: bool = False,
    icon_path: Path | None = None,
) -> object:
    """Start the tray icon on a daemon thread."""
    import threading

    import pystray
    from PIL import Image

    from alices_clip.runtime import launch_spec

    image: Image.Image
    if icon_path is not None and icon_path.is_file():
        image = Image.open(icon_path)
    else:
        image = build_tray_icon()

    def _uninstall() -> None:
        program, prefix = launch_spec()
        cmd = [program]
        if prefix:
            cmd.extend(prefix.split())
        cmd.append("--uninstall")
        subprocess.Popen(cmd, close_fds=True)

    def _open_folder() -> None:
        if on_open_folder is not None:
            on_open_folder()

    items = [
        pystray.MenuItem("Open bag", lambda: on_open(), default=True),
    ]
    if on_open_folder is not None:
        items.append(pystray.MenuItem("Open clips folder", lambda: _open_folder()))
    if on_toggle_pause is not None:
        label = "Resume monitoring" if paused else "Pause monitoring"
        items.append(pystray.MenuItem(label, lambda: on_toggle_pause()))
    if on_clear_bag is not None:
        items.append(pystray.MenuItem("Clear bag…", lambda: on_clear_bag()))
    if on_settings is not None:
        items.append(pystray.MenuItem("Settings…", lambda: on_settings()))
    items.extend(
        [
            pystray.MenuItem("Uninstall…", lambda: _uninstall()),
            pystray.MenuItem("Quit", lambda: on_quit()),
        ]
    )
    menu = pystray.Menu(*items)
    icon = pystray.Icon("alices_clip_of_holding", image, "Alice's Clip of Holding", menu)
    thread = threading.Thread(target=icon.run, name="alice-tray", daemon=True)
    thread.start()
    return icon

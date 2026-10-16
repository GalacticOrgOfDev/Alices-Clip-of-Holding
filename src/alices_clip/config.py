"""Application paths and user-tunable settings."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

APP_ID = "AlicesClipOfHolding"
APP_TITLE = "Alice's Clip of Holding"

# Common virtual-key codes for the settings UI
VK_NAMES = {
    0x56: "V",
    0x43: "C",
    0x58: "X",
    0x5A: "Z",
    0x41: "A",
    0x53: "S",
    0x44: "D",
    0x46: "F",
    0x47: "G",
    0x48: "H",
    0x4A: "J",
    0x4B: "K",
    0x4C: "L",
}


def default_data_dir() -> Path:
    """Return the per-user data directory for the bag.

    Returns:
        ``%LOCALAPPDATA%\\AlicesClipOfHolding`` on Windows, or
        ``~/.local/share/AlicesClipOfHolding`` elsewhere.
    """
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        return Path(local_app) / APP_ID
    return Path.home() / ".local" / "share" / APP_ID


@dataclass
class AppConfig:
    """User settings persisted as ``config.json`` next to the clip bag.

    Attributes:
        max_clips: Oldest unpinned clips are pruned once this count is exceeded.
        poll_ms: Clipboard sequence poll interval in milliseconds.
        intercept_picker: When True, the picker hotkey opens the bag.
        picker_vk: Virtual-key code for the picker hotkey (default VK_V).
        picker_ctrl: Require Control for the picker hotkey.
        picker_shift: Require Shift for the picker hotkey.
        allow_native: When True, the native hotkey pastes the OS clipboard.
        native_vk: Virtual-key code for the native paste hotkey.
        native_ctrl: Require Control for the native hotkey.
        native_shift: Require Shift for the native hotkey.
        start_with_windows: Installer writes a Startup shortcut when True.
        monitoring_paused: When True, clipboard polling is skipped.
    """

    max_clips: int = 200
    poll_ms: int = 250
    intercept_picker: bool = True
    picker_vk: int = 0x56  # VK_V
    picker_ctrl: bool = True
    picker_shift: bool = False
    allow_native: bool = True
    native_vk: int = 0x56  # VK_V
    native_ctrl: bool = True
    native_shift: bool = True
    start_with_windows: bool = True
    monitoring_paused: bool = False

    def clips_dir(self, data_dir: Path) -> Path:
        """Return the folder that holds individual clip directories."""
        return data_dir / "clips"

    def index_path(self, data_dir: Path) -> Path:
        """Return the path of the bag index file."""
        return data_dir / "index.json"

    def hotkey_label(self, vk: int, ctrl: bool, shift: bool) -> str:
        """Human-readable hotkey string for menus and the picker."""
        parts = []
        if ctrl:
            parts.append("Ctrl")
        if shift:
            parts.append("Shift")
        parts.append(VK_NAMES.get(vk, f"VK_{vk:02X}"))
        return "+".join(parts)


def load_config(data_dir: Path) -> AppConfig:
    """Load ``config.json`` or create it with defaults.

    Args:
        data_dir: Per-user application data directory.

    Returns:
        The loaded or newly written ``AppConfig``.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "config.json"
    if not path.is_file():
        config = AppConfig()
        save_config(data_dir, config)
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOGGER.error("Failed to read %s; using defaults", path, exc_info=True)
        return AppConfig()
    defaults = asdict(AppConfig())
    defaults.update({key: raw[key] for key in defaults if key in raw})
    # Migrate old keys if present
    if "intercept_ctrl_v" in raw:
        defaults["intercept_picker"] = bool(raw["intercept_ctrl_v"])
    if "allow_native_ctrl_shift_v" in raw:
        defaults["allow_native"] = bool(raw["allow_native_ctrl_shift_v"])
    return AppConfig(**defaults)


def save_config(data_dir: Path, config: AppConfig) -> None:
    """Write ``config.json`` atomically enough for a single-user app.

    Args:
        data_dir: Per-user application data directory.
        config: Settings to persist.

    Raises:
        OSError: If the file cannot be written.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "config.json"
    path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")

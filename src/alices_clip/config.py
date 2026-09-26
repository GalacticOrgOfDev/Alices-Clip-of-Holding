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
        max_clips: Oldest clips are pruned once this count is exceeded.
        poll_ms: Clipboard sequence poll interval in milliseconds.
        intercept_ctrl_v: When True, Ctrl+V opens the picker.
        allow_native_ctrl_shift_v: When True, Ctrl+Shift+V pastes the OS
            clipboard without opening the picker.
        start_with_windows: Installer writes a Startup shortcut when True.
    """

    max_clips: int = 200
    poll_ms: int = 250
    intercept_ctrl_v: bool = True
    allow_native_ctrl_shift_v: bool = True
    start_with_windows: bool = True

    def clips_dir(self, data_dir: Path) -> Path:
        """Return the folder that holds individual clip directories."""
        return data_dir / "clips"

    def index_path(self, data_dir: Path) -> Path:
        """Return the path of the bag index file."""
        return data_dir / "index.json"


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

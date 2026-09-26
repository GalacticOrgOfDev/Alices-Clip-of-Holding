"""Frozen-exe vs source-tree path helpers."""

from __future__ import annotations

import sys
from pathlib import Path

from alices_clip.config import APP_ID, default_data_dir


def is_frozen() -> bool:
    """Return True when running from a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False))


def current_executable() -> Path:
    """Return the path of the process image the user launched.

    Returns:
        The packaged ``.exe`` when frozen, otherwise ``sys.executable``.
    """
    return Path(sys.executable).resolve()


def install_bin_dir() -> Path:
    """Return the per-user directory that holds the installed executable."""
    return default_data_dir() / "bin"


def installed_executable() -> Path:
    """Return the canonical installed exe path."""
    return install_bin_dir() / "AlicesClipOfHolding.exe"


def running_from_install() -> bool:
    """Return True when this process already is the installed copy."""
    try:
        return current_executable() == installed_executable()
    except OSError:
        return False


def launch_spec() -> tuple[str, str]:
    """Return ``(program, arguments)`` used for shortcuts and shell verbs."""
    if is_frozen():
        return str(installed_executable()), ""
    return sys.executable, "-m alices_clip"


def command_for(flag: str, extra: str = "") -> str:
    """Build a registry command string that keeps ``%1`` / ``%V`` intact."""
    program, prefix = launch_spec()
    parts = [f'"{program}"']
    if prefix:
        parts.append(prefix)
    parts.append(flag)
    if extra:
        parts.append(extra)
    return " ".join(parts)


def app_id() -> str:
    """Return the stable application id used in registry keys."""
    return APP_ID

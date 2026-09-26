"""Talk to the live Explorer window so multi-select context menus work.

Static registry verbs only pass the first selected path. When the user
right-clicks a multi-selection we ask the foreground Explorer window for
every selected item through ``Shell.Application``.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def selected_explorer_paths(fallback: list[Path]) -> list[Path]:
    """Return Explorer's current selection, or ``fallback`` if none."""
    discovered = _query_explorer_selection()
    if discovered:
        return discovered
    return [path for path in fallback if path.exists()]


def _query_explorer_selection() -> list[Path]:
    """Ask Shell.Application for SelectedItems on visible Explorer windows."""
    try:
        import win32gui
        import win32com.client
    except ImportError:
        LOGGER.error("pywin32 is required for Explorer selection", exc_info=True)
        return []

    foreground = int(win32gui.GetForegroundWindow() or 0)
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        windows = list(shell.Windows())
    except Exception:
        LOGGER.error("Shell.Application is unavailable", exc_info=True)
        return []

    ranked: list[tuple[int, list[Path]]] = []
    for window in windows:
        try:
            hwnd = int(window.HWND)
            doc = window.Document
            if doc is None:
                continue
            selected = [Path(str(item.Path)) for item in doc.SelectedItems()]
            selected = [path for path in selected if path.exists()]
            if not selected:
                continue
            score = 0 if hwnd == foreground else 1
            ranked.append((score, selected))
        except Exception:
            LOGGER.error("Skipping an Explorer window during selection query", exc_info=True)

    if not ranked:
        return []
    ranked.sort(key=lambda item: item[0])
    return _unique(ranked[0][1])


def _unique(paths: list[Path]) -> list[Path]:
    """Preserve order while dropping duplicate paths."""
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result

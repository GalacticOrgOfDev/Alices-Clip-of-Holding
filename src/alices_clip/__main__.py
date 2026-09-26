"""Module and frozen-exe entry point."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from alices_clip.app import AliceApp, configure_logging, run_folder_paste_picker
from alices_clip.config import default_data_dir
from alices_clip.runtime import is_frozen, running_from_install

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Dispatch install, uninstall, shell verbs, or the tray app."""
    parser = argparse.ArgumentParser(prog="AlicesClipOfHolding")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--keep-clips", action="store_true")
    parser.add_argument("--delete-clips", action="store_true")
    parser.add_argument("--shell-copy", nargs="*", default=None)
    parser.add_argument("--shell-paste", nargs="?", const="")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(data_dir)

    if args.uninstall:
        return _uninstall(args.keep_clips, args.delete_clips)
    if args.install:
        return _install_and_maybe_start(start=False)
    if args.shell_copy is not None:
        return _shell_copy(args.shell_copy)
    if args.shell_paste is not None:
        return _shell_paste(args.shell_paste)

    if sys.platform == "win32":
        from alices_clip.windows_install import is_registered

        if not is_registered():
            return _install_and_maybe_start(start=True)
        if is_frozen() and not running_from_install():
            return _install_and_maybe_start(start=True)

    app = AliceApp()
    return app.run()


def _install_and_maybe_start(start: bool) -> int:
    """Register Windows integration, then optionally launch the tray app."""
    from alices_clip.windows_install import install_product

    target = install_product()
    if not start:
        return 0
    if is_frozen() and target.exists() and target.resolve() != Path(sys.executable).resolve():
        subprocess.Popen([str(target)], close_fds=True)
        return 0
    app = AliceApp()
    return app.run()


def _uninstall(keep: bool, delete: bool) -> int:
    """Run the uninstall prompt unless the caller already chose."""
    from alices_clip.uninstall_ui import ask_uninstall
    from alices_clip.windows_install import uninstall_product

    delete_clips: bool | None
    if delete and keep:
        LOGGER.error("Pass only one of --keep-clips or --delete-clips")
        return 2
    if delete:
        delete_clips = True
    elif keep:
        delete_clips = False
    else:
        delete_clips = ask_uninstall()
    if delete_clips is None:
        return 1
    uninstall_product(delete_clips=delete_clips)
    return 0


def _shell_copy(raw_paths: list[str]) -> int:
    """Archive the Explorer selection into the bag."""
    from alices_clip.actions import ingest_paths
    from alices_clip.explorer import selected_explorer_paths

    fallback = [Path(item) for item in raw_paths if item]
    record = ingest_paths(selected_explorer_paths(fallback))
    return 0 if record is not None else 1


def _shell_paste(raw_dir: str) -> int:
    """Open the picker and write the chosen clip into an Explorer folder."""
    destination = Path(raw_dir) if raw_dir else Path.cwd()
    if not destination.is_dir():
        LOGGER.error("Paste target is not a directory: %s", destination)
        return 2
    return run_folder_paste_picker(destination)


if __name__ == "__main__":
    sys.exit(main())

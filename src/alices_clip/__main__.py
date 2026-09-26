"""Module entry point: ``python -m alices_clip``."""

from __future__ import annotations

import sys

from alices_clip.app import AliceApp, configure_logging
from alices_clip.config import default_data_dir


def main() -> int:
    """Boot the tray application.

    Returns:
        Process exit code.
    """
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(data_dir)
    app = AliceApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())

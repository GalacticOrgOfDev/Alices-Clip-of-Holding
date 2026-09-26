"""Composition root: clipboard poll, hotkeys, picker, and tray."""

from __future__ import annotations

import logging
import sys
import tkinter as tk

from alices_clip.config import APP_TITLE, AppConfig, default_data_dir, load_config
from alices_clip.hotkeys import HotkeyEvent, HotkeyHook, send_ctrl_v
from alices_clip.models import ClipRecord
from alices_clip.picker import ClipPicker
from alices_clip.storage import ClipStore
from alices_clip.tray import start_tray
from alices_clip.win_clipboard import ClipboardBag

LOGGER = logging.getLogger(__name__)


class AliceApp:
    """Long-running tray application that owns the Tk main loop."""

    def __init__(self, config: AppConfig | None = None) -> None:
        """Build every subsystem but do not start loops yet.

        Args:
            config: Optional override used by tests. Production loads
                ``config.json`` from the per-user data directory.
        """
        self.data_dir = default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config = config if config is not None else load_config(self.data_dir)
        self.store = ClipStore(self.data_dir, self.config)
        self.bag = ClipboardBag(self.store)
        self.hook = HotkeyHook(
            intercept_ctrl_v=self.config.intercept_ctrl_v,
            allow_native_ctrl_shift_v=self.config.allow_native_ctrl_shift_v,
        )
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_TITLE)
        self.picker = ClipPicker(
            self.root,
            self.store,
            on_pick=self._paste_record,
            on_cancel=lambda: None,
        )
        self.tray_icon = None
        self._running = False

    def run(self) -> int:
        """Start hooks, tray, and the Tk loop.

        Returns:
            Process exit code. ``0`` on a clean quit.
        """
        if sys.platform != "win32":
            LOGGER.error("Alice's Clip of Holding requires Windows.")
            return 2
        self._running = True
        self.hook.start()
        self.tray_icon = start_tray(on_open=self._open_picker_safe, on_quit=self.stop)
        self.root.after(self.config.poll_ms, self._tick)
        LOGGER.info("Alice's Clip of Holding is running. Bag: %s", self.data_dir)
        try:
            self.root.mainloop()
        finally:
            self._running = False
        return 0

    def stop(self) -> None:
        """Tear down tray, hook, and Tk.

        Notes:
            Tray and Tk teardown can raise if the window is already gone.
            Those failures are logged and must not block process exit.
        """
        self._running = False
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                LOGGER.error("Tray icon stop failed", exc_info=True)
        self.hook.stop()
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            LOGGER.error("Tk destroy failed", exc_info=True)

    def _tick(self) -> None:
        """One main-loop quantum: clipboard poll + hotkey drain.

        Notes:
            Clipboard and hook failures are isolated so one bad paste
            event cannot kill the tray process.
        """
        if not self._running:
            return
        try:
            self.bag.poll()
        except Exception:
            LOGGER.error("Clipboard poll failed", exc_info=True)
        try:
            for event in self.hook.drain():
                if event is HotkeyEvent.OPEN_PICKER:
                    self.picker.open()
                elif event is HotkeyEvent.NATIVE_PASTE:
                    pass
        except Exception:
            LOGGER.error("Hotkey drain failed", exc_info=True)
        self.root.after(self.config.poll_ms, self._tick)

    def _open_picker_safe(self) -> None:
        """Open the picker from the tray thread via the Tk loop."""
        self.root.after(0, self.picker.open)

    def _paste_record(self, record: ClipRecord) -> None:
        """Restore ``record`` onto the OS clipboard and send Ctrl+V.

        Args:
            record: Clip chosen in the picker.
        """
        restored = self.bag.restore_to_clipboard(record)
        if not restored:
            LOGGER.error("Could not restore clip %s", record.clip_id)
            return
        self.hook.begin_injected_paste()

        def _send() -> None:
            try:
                send_ctrl_v()
            finally:
                self.root.after(400, self.hook.end_injected_paste)

        self.root.after(40, _send)


def configure_logging(data_dir) -> None:
    """Write logs next to the bag so install problems are diagnosable.

    Args:
        data_dir: Per-user application data directory.
    """
    log_path = data_dir / "alice.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

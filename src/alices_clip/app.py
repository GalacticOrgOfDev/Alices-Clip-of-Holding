"""Composition root: clipboard poll, hotkeys, picker, and tray."""

from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from alices_clip.actions import paste_record_into_directory
from alices_clip.config import APP_TITLE, AppConfig, VK_NAMES, default_data_dir, load_config, save_config
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
        """Build every subsystem but do not start loops yet."""
        self.data_dir = default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config = config if config is not None else load_config(self.data_dir)
        self.store = ClipStore(self.data_dir, self.config)
        self.bag = ClipboardBag(self.store)
        self.hook = HotkeyHook(
            intercept_picker=self.config.intercept_picker,
            picker_vk=self.config.picker_vk,
            picker_ctrl=self.config.picker_ctrl,
            picker_shift=self.config.picker_shift,
            allow_native=self.config.allow_native,
            native_vk=self.config.native_vk,
            native_ctrl=self.config.native_ctrl,
            native_shift=self.config.native_shift,
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
        """Start hooks, tray, and the Tk loop."""
        if sys.platform != "win32":
            LOGGER.error("Alice's Clip of Holding requires Windows.")
            return 2
        self._running = True
        self.hook.start()
        self.tray_icon = start_tray(
            on_open=self._open_picker_safe,
            on_quit=self.stop,
            on_settings=self._open_settings,
            on_open_folder=self._open_clips_folder,
            on_toggle_pause=self._toggle_pause,
            on_clear_bag=self._clear_bag,
            paused=self.config.monitoring_paused,
        )
        self.root.after(self.config.poll_ms, self._tick)
        LOGGER.info("Alice's Clip of Holding is running. Bag: %s", self.data_dir)
        try:
            self.root.mainloop()
        finally:
            self._running = False
        return 0

    def stop(self) -> None:
        """Tear down tray, hook, and Tk."""
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
        """One main-loop quantum: clipboard poll + hotkey drain."""
        if not self._running:
            return
        if not self.config.monitoring_paused:
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

    def _open_clips_folder(self) -> None:
        """Open the clips directory in Explorer."""
        folder = self.store.clips_dir
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder))

    def _toggle_pause(self) -> None:
        """Toggle clipboard monitoring and refresh the tray."""
        self.config.monitoring_paused = not self.config.monitoring_paused
        save_config(self.data_dir, self.config)
        # Recreate tray so the menu label updates
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.tray_icon = start_tray(
            on_open=self._open_picker_safe,
            on_quit=self.stop,
            on_settings=self._open_settings,
            on_open_folder=self._open_clips_folder,
            on_toggle_pause=self._toggle_pause,
            on_clear_bag=self._clear_bag,
            paused=self.config.monitoring_paused,
        )

    def _clear_bag(self) -> None:
        """Ask confirmation then remove every clip."""
        def _do() -> None:
            if not messagebox.askyesno(
                "Clear bag",
                "Delete every clip in the bag? Pinned clips will also be removed.",
                parent=self.root,
            ):
                return
            for record in list(self.store.records()):
                self.store.remove(record.clip_id)
            messagebox.showinfo("Clear bag", "Bag cleared.", parent=self.root)

        self.root.after(0, _do)

    def _open_settings(self) -> None:
        """Open a simple settings dialog from the tray."""
        self.root.after(0, self._show_settings_dialog)

    def _show_settings_dialog(self) -> None:
        """Modal settings window for clips, poll, and hotkeys."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Alice Settings")
        dlg.attributes("-topmost", True)
        dlg.geometry("480x420")
        dlg.resizable(False, False)

        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Maximum clips kept (pinned always stay)", font=("Segoe UI", 10)).pack(anchor="w")
        max_var = tk.IntVar(value=self.config.max_clips)
        ttk.Spinbox(frame, from_=10, to=5000, textvariable=max_var, width=10).pack(anchor="w", pady=(4, 8))

        ttk.Label(frame, text="Clipboard poll interval (ms)", font=("Segoe UI", 10)).pack(anchor="w")
        poll_var = tk.IntVar(value=self.config.poll_ms)
        ttk.Spinbox(frame, from_=50, to=2000, textvariable=poll_var, width=10).pack(anchor="w", pady=(4, 12))

        # Picker hotkey
        ttk.Label(frame, text="Picker hotkey", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        intercept_var = tk.BooleanVar(value=self.config.intercept_picker)
        ttk.Checkbutton(frame, text="Enable picker hotkey", variable=intercept_var).pack(anchor="w")
        picker_ctrl = tk.BooleanVar(value=self.config.picker_ctrl)
        picker_shift = tk.BooleanVar(value=self.config.picker_shift)
        ttk.Checkbutton(frame, text="Require Ctrl", variable=picker_ctrl).pack(anchor="w")
        ttk.Checkbutton(frame, text="Require Shift", variable=picker_shift).pack(anchor="w")
        picker_vk_var = tk.StringVar(value=VK_NAMES.get(self.config.picker_vk, "V"))
        ttk.Label(frame, text="Key").pack(anchor="w")
        ttk.Combobox(frame, textvariable=picker_vk_var, values=list(VK_NAMES.values()), width=6, state="readonly").pack(anchor="w", pady=(0, 8))

        # Native hotkey
        ttk.Label(frame, text="Native paste hotkey", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 2))
        native_var = tk.BooleanVar(value=self.config.allow_native)
        ttk.Checkbutton(frame, text="Enable native paste hotkey", variable=native_var).pack(anchor="w")
        native_ctrl = tk.BooleanVar(value=self.config.native_ctrl)
        native_shift = tk.BooleanVar(value=self.config.native_shift)
        ttk.Checkbutton(frame, text="Require Ctrl", variable=native_ctrl).pack(anchor="w")
        ttk.Checkbutton(frame, text="Require Shift", variable=native_shift).pack(anchor="w")
        native_vk_var = tk.StringVar(value=VK_NAMES.get(self.config.native_vk, "V"))
        ttk.Label(frame, text="Key").pack(anchor="w")
        ttk.Combobox(frame, textvariable=native_vk_var, values=list(VK_NAMES.values()), width=6, state="readonly").pack(anchor="w", pady=(0, 8))

        def _vk_from_name(name: str) -> int:
            for code, label in VK_NAMES.items():
                if label == name:
                    return code
            return 0x56

        def _save() -> None:
            try:
                new_max = int(max_var.get())
                new_poll = int(poll_var.get())
                if new_max < 1 or new_poll < 50:
                    raise ValueError
            except (tk.TclError, ValueError):
                messagebox.showerror("Settings", "Max clips and poll interval must be positive integers.", parent=dlg)
                return
            self.config.max_clips = new_max
            self.config.poll_ms = new_poll
            self.config.intercept_picker = bool(intercept_var.get())
            self.config.picker_ctrl = bool(picker_ctrl.get())
            self.config.picker_shift = bool(picker_shift.get())
            self.config.picker_vk = _vk_from_name(picker_vk_var.get())
            self.config.allow_native = bool(native_var.get())
            self.config.native_ctrl = bool(native_ctrl.get())
            self.config.native_shift = bool(native_shift.get())
            self.config.native_vk = _vk_from_name(native_vk_var.get())
            save_config(self.data_dir, self.config)
            self.store.config = self.config
            messagebox.showinfo(
                "Settings",
                "Saved. Hotkey changes apply on next launch.",
                parent=dlg,
            )
            dlg.destroy()

        btns = ttk.Frame(frame)
        btns.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(btns, text="Save", command=_save).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)

        dlg.transient(self.root)
        dlg.grab_set()
        dlg.focus_set()

    def _paste_record(self, record: ClipRecord) -> None:
        """Restore ``record`` onto the OS clipboard and send Ctrl+V."""
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


def run_folder_paste_picker(destination: Path) -> int:
    """Open the bag picker and write the chosen clip into ``destination``."""
    target = Path(destination)
    app = AliceApp()
    chosen = {"ok": False}

    def _on_pick(record: ClipRecord) -> None:
        paste_record_into_directory(record, target)
        chosen["ok"] = True
        app.stop()

    def _on_cancel() -> None:
        app.stop()

    app.picker.on_pick = _on_pick
    app.picker.on_cancel = _on_cancel
    app.root.after(0, app.picker.open)
    app.root.mainloop()
    return 0 if chosen["ok"] else 1


def configure_logging(data_dir) -> None:
    """Write logs next to the bag so install problems are diagnosable."""
    log_path = data_dir / "alice.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

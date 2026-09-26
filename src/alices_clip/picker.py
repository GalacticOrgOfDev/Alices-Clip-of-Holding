"""Tkinter paste picker over the clip bag."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from alices_clip.config import APP_TITLE
from alices_clip.models import ClipKind, ClipRecord
from alices_clip.storage import ClipStore

LOGGER = logging.getLogger(__name__)

KIND_LABEL = {
    ClipKind.TEXT: "TEXT",
    ClipKind.IMAGE: "IMAGE",
    ClipKind.FILE: "FILE",
    ClipKind.HTML: "HTML",
    ClipKind.RTF: "RTF",
    ClipKind.BINARY: "BIN",
}


class ClipPicker:
    """Always-on-top chooser that returns a clip id to paste."""

    def __init__(
        self,
        root: tk.Tk,
        store: ClipStore,
        on_pick: Callable[[ClipRecord], None],
        on_cancel: Callable[[], None],
    ) -> None:
        """Bind the picker to the hidden Tk root.

        Args:
            root: Hidden application root. The picker is a ``Toplevel``.
            store: Live clip store used to populate the list.
            on_pick: Called with the chosen record after the window closes.
            on_cancel: Called when the user dismisses the picker.
        """
        self.root = root
        self.store = store
        self.on_pick = on_pick
        self.on_cancel = on_cancel
        self.window: tk.Toplevel | None = None
        self.listbox: tk.Listbox | None = None
        self.search_var = tk.StringVar()
        self._visible: list[ClipRecord] = []

    def is_open(self) -> bool:
        """Return True when the picker window exists."""
        return self.window is not None and self.window.winfo_exists()

    def open(self) -> None:
        """Show or raise the picker near the current pointer."""
        if self.is_open() and self.window is not None:
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            self._reload()
            return
        window = tk.Toplevel(self.root)
        self.window = window
        window.title(APP_TITLE)
        window.attributes("-topmost", True)
        window.resizable(True, True)
        window.geometry("640x420")
        window.protocol("WM_DELETE_WINDOW", self._cancel)

        chrome = ttk.Frame(window, padding=10)
        chrome.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            chrome,
            text="Alice's Clip of Holding  —  choose what to paste",
            font=("Segoe UI", 11, "bold"),
        )
        header.pack(anchor="w")
        hint = ttk.Label(
            chrome,
            text="Enter paste · Esc close · Delete drop from bag · Ctrl+Shift+V native last item",
            font=("Segoe UI", 8),
        )
        hint.pack(anchor="w", pady=(0, 8))

        search = ttk.Entry(chrome, textvariable=self.search_var)
        search.pack(fill=tk.X, pady=(0, 8))
        self.search_var.trace_add("write", lambda *_args: self._reload())

        listbox = tk.Listbox(
            chrome,
            activestyle="dotbox",
            font=("Consolas", 10),
            selectmode=tk.SINGLE,
        )
        listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox = listbox
        listbox.bind("<Double-Button-1>", lambda _event: self._confirm())
        listbox.bind("<Return>", lambda _event: self._confirm())
        listbox.bind("<Escape>", lambda _event: self._cancel())
        listbox.bind("<Delete>", lambda _event: self._delete_selected())

        buttons = ttk.Frame(chrome)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Paste", command=self._confirm).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Delete", command=self._delete_selected).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Close", command=self._cancel).pack(side=tk.RIGHT)

        self._place_near_pointer(window)
        self._reload()
        search.focus_set()
        window.bind("<Return>", lambda _event: self._confirm())
        window.bind("<Escape>", lambda _event: self._cancel())

    def close(self) -> None:
        """Destroy the picker window if it is open."""
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                LOGGER.error("Picker window already destroyed", exc_info=True)
            self.window = None
            self.listbox = None

    def _place_near_pointer(self, window: tk.Toplevel) -> None:
        """Move the picker near the mouse so it feels like a context menu."""
        try:
            x = window.winfo_pointerx() - 80
            y = window.winfo_pointery() - 40
        except tk.TclError:
            x, y = 200, 200
        window.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _reload(self) -> None:
        """Refill the listbox from the store, applying the search filter."""
        if self.listbox is None:
            return
        needle = self.search_var.get().strip().lower()
        records = self.store.records()
        if needle:
            records = [
                record
                for record in records
                if needle in record.preview.lower()
                or needle in record.kind.value
                or needle in record.primary_name.lower()
            ]
        self._visible = records
        self.listbox.delete(0, tk.END)
        for record in records:
            badge = KIND_LABEL.get(record.kind, record.kind.value.upper())
            stamp = record.created_iso.replace("T", " ")
            line = f"[{badge:<5}]  {stamp}   {record.preview or record.primary_name}"
            self.listbox.insert(tk.END, line)
        if records:
            self.listbox.selection_set(0)
            self.listbox.activate(0)

    def _selected(self) -> ClipRecord | None:
        """Return the highlighted record, or None."""
        if self.listbox is None:
            return None
        selection = self.listbox.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index < 0 or index >= len(self._visible):
            return None
        return self._visible[index]

    def _confirm(self) -> None:
        """Paste the highlighted clip and close."""
        record = self._selected()
        self.close()
        if record is None:
            self.on_cancel()
            return
        self.on_pick(record)

    def _cancel(self) -> None:
        """Close without pasting."""
        self.close()
        self.on_cancel()

    def _delete_selected(self) -> None:
        """Remove the highlighted clip from the bag."""
        record = self._selected()
        if record is None:
            return
        self.store.remove(record.clip_id)
        self._reload()

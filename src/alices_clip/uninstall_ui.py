"""Uninstall dialog: keep or clear the clip bag."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from alices_clip.config import APP_TITLE, default_data_dir


def ask_uninstall() -> bool | None:
    """Show the keep / delete / cancel prompt.

    Returns:
        True to delete clip files, False to keep them, None if cancelled.
    """
    result: dict[str, bool | None] = {"value": None}
    root = tk.Tk()
    root.title(f"Uninstall {APP_TITLE}")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill=tk.BOTH, expand=True)

    ttk.Label(frame, text=f"Uninstall {APP_TITLE}?", font=("Segoe UI", 12, "bold")).pack(
        anchor="w"
    )
    ttk.Label(
        frame,
        text=(
            "This removes the tray app, Start Menu / Apps entry, and Explorer "
            "context-menu items.\n\nYour bag of clips lives in:\n"
            f"{default_data_dir() / 'clips'}"
        ),
        justify=tk.LEFT,
        wraplength=420,
    ).pack(anchor="w", pady=(8, 16))

    def choose(value: bool | None) -> None:
        result["value"] = value
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X)
    ttk.Button(buttons, text="Uninstall and keep clips", command=lambda: choose(False)).pack(
        side=tk.LEFT
    )
    ttk.Button(buttons, text="Uninstall and delete clips", command=lambda: choose(True)).pack(
        side=tk.LEFT, padx=8
    )
    ttk.Button(buttons, text="Cancel", command=lambda: choose(None)).pack(side=tk.RIGHT)

    root.protocol("WM_DELETE_WINDOW", lambda: choose(None))
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = max((root.winfo_screenwidth() - width) // 2, 0)
    y = max((root.winfo_screenheight() - height) // 3, 0)
    root.geometry(f"+{x}+{y}")
    root.mainloop()
    return result["value"]

"""Per-user install, Explorer verbs, Apps & Features entry, and uninstall."""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from alices_clip.config import APP_ID, APP_TITLE, default_data_dir
from alices_clip.runtime import (
    command_for,
    current_executable,
    install_bin_dir,
    installed_executable,
    is_frozen,
    launch_spec,
)

LOGGER = logging.getLogger(__name__)
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
VERSION = "1.1.0"
SHELL_VERBS = (
    (r"Software\Classes\*\shell\AlicesClipCopy", "Copy to Alice's Clip of Holding", "--shell-copy", '"%1"'),
    (
        r"Software\Classes\AllFilesystemObjects\shell\AlicesClipCopy",
        "Copy to Alice's Clip of Holding",
        "--shell-copy",
        '"%1"',
    ),
    (
        r"Software\Classes\Directory\shell\AlicesClipPaste",
        "Paste from Alice's Clip of Holding",
        "--shell-paste",
        '"%1"',
    ),
    (
        r"Software\Classes\Directory\Background\shell\AlicesClipPaste",
        "Paste from Alice's Clip of Holding",
        "--shell-paste",
        '"%V"',
    ),
)


def install_product() -> Path:
    """Copy the exe into the per-user bin dir and register Windows integration."""
    default_data_dir().mkdir(parents=True, exist_ok=True)
    target = _stage_executable()
    _write_shortcuts(target)
    _register_uninstall(target)
    _register_shell_verbs()
    _notify_shell()
    LOGGER.info("Installed %s to %s", APP_TITLE, target)
    return target


def uninstall_product(*, delete_clips: bool) -> None:
    """Remove shortcuts, verbs, Apps entry, and optionally the clip bag."""
    _unregister_shell_verbs()
    _delete_shortcuts()
    _unregister_uninstall()
    _stop_running_instances()
    data_dir = default_data_dir()
    bin_dir = install_bin_dir()
    if delete_clips:
        if data_dir.is_dir():
            shutil.rmtree(data_dir, ignore_errors=True)
    else:
        if bin_dir.is_dir():
            shutil.rmtree(bin_dir, ignore_errors=True)
        for leftover in ("start.cmd", "venv"):
            path = data_dir / leftover
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
    _notify_shell()
    LOGGER.info("Uninstalled %s (delete_clips=%s)", APP_TITLE, delete_clips)


def is_registered() -> bool:
    """Return True when the Apps & Features uninstall key exists."""
    try:
        import winreg
    except ImportError:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def _stage_executable() -> Path:
    """Place a durable launch target under LocalAppData."""
    if is_frozen():
        dest = installed_executable()
        dest.parent.mkdir(parents=True, exist_ok=True)
        source = current_executable()
        if source != dest:
            shutil.copy2(source, dest)
        return dest
    return Path(launch_spec()[0])


def _write_shortcuts(target: Path) -> None:
    """Create Startup, Desktop, and Start Menu shortcuts."""
    program, args = launch_spec()
    _write_shortcut(_startup_dir() / f"{APP_TITLE}.lnk", program, args, 7)
    _write_shortcut(_desktop_dir() / f"{APP_TITLE}.lnk", program, args, 1)
    start_dir = _start_menu_dir()
    start_dir.mkdir(parents=True, exist_ok=True)
    _write_shortcut(start_dir / f"{APP_TITLE}.lnk", program, args, 1)
    _write_shortcut(start_dir / f"Uninstall {APP_TITLE}.lnk", program, f"{args} --uninstall".strip(), 1)
    del target


def _write_shortcut(path: Path, program: str, args: str, window_style: int) -> None:
    """Write a .lnk via WScript.Shell."""
    try:
        import win32com.client
    except ImportError:
        LOGGER.error("Cannot write shortcut %s without pywin32", path, exc_info=True)
        return
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(path))
    shortcut.TargetPath = program
    shortcut.Arguments = args
    shortcut.WorkingDirectory = str(default_data_dir())
    shortcut.WindowStyle = window_style
    shortcut.Description = APP_TITLE
    if Path(program).suffix.lower() == ".exe":
        shortcut.IconLocation = program
    shortcut.Save()


def _delete_shortcuts() -> None:
    """Remove every shortcut this installer creates."""
    start_dir = _start_menu_dir()
    for path in (
        _startup_dir() / f"{APP_TITLE}.lnk",
        _desktop_dir() / f"{APP_TITLE}.lnk",
        start_dir / f"{APP_TITLE}.lnk",
        start_dir / f"Uninstall {APP_TITLE}.lnk",
    ):
        if path.is_file():
            path.unlink(missing_ok=True)
    if start_dir.is_dir() and not any(start_dir.iterdir()):
        start_dir.rmdir()


def _register_uninstall(target: Path) -> None:
    """Write the per-user Apps & Features row."""
    import winreg

    program, args = launch_spec()
    uninstall = f'"{program}" {args} --uninstall'.replace("  ", " ").strip()
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    values = {
        "DisplayName": APP_TITLE,
        "DisplayVersion": VERSION,
        "Publisher": "Galactic Organization of Development",
        "UninstallString": uninstall,
        "DisplayIcon": str(target) if target.suffix.lower() == ".exe" else program,
        "InstallLocation": str(default_data_dir()),
        "HelpLink": "https://github.com/GalacticOrgOfDev/Alices-Clip-of-Holding",
        "URLInfoAbout": "https://github.com/GalacticOrgOfDev/Alices-Clip-of-Holding",
    }
    for name, value in values.items():
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
    winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    winreg.CloseKey(key)


def _unregister_uninstall() -> None:
    """Delete the Apps & Features row."""
    import winreg

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        return
    except OSError:
        LOGGER.error("Failed to delete uninstall key", exc_info=True)


def _register_shell_verbs() -> None:
    """Install Explorer context-menu verbs."""
    import winreg

    for key_path, title, flag, extra in SHELL_VERBS:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, title)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, launch_spec()[0])
        winreg.SetValueEx(key, "Position", 0, winreg.REG_SZ, "Top")
        winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        command_key = winreg.CreateKey(key, "command")
        winreg.SetValueEx(command_key, None, 0, winreg.REG_SZ, command_for(flag, extra))
        winreg.CloseKey(command_key)
        winreg.CloseKey(key)


def _unregister_shell_verbs() -> None:
    """Remove Explorer verbs."""
    import winreg

    for key_path, _title, _flag, _extra in SHELL_VERBS:
        _delete_key_tree(winreg.HKEY_CURRENT_USER, key_path)


def _delete_key_tree(root, path: str) -> None:
    """Delete a registry key and its descendants."""
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_key_tree(root, path + "\\" + child)
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        return
    except OSError:
        LOGGER.error("Failed to delete registry key %s", path, exc_info=True)


def _notify_shell() -> None:
    """Ask Explorer to reload associations."""
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        LOGGER.error("SHChangeNotify failed", exc_info=True)


def _stop_running_instances() -> None:
    """Best-effort stop of other Alice windows so files can be deleted."""
    if sys.platform != "win32":
        return
    current_pid = os.getpid()
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return

    def _enum(hwnd, _ctx) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        if win32gui.GetWindowText(hwnd) != APP_TITLE:
            return
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        del _tid
        if pid == current_pid:
            return
        try:
            handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
            win32api.TerminateProcess(handle, 0)
            win32api.CloseHandle(handle)
        except Exception:
            LOGGER.error("Could not stop process %s", pid, exc_info=True)

    try:
        win32gui.EnumWindows(_enum, None)
    except Exception:
        LOGGER.error("EnumWindows failed during uninstall", exc_info=True)


def _startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs\Startup"


def _desktop_dir() -> Path:
    return Path.home() / "Desktop"


def _start_menu_dir() -> Path:
    return Path(os.environ["APPDATA"]) / r"Microsoft\Windows\Start Menu\Programs" / APP_TITLE

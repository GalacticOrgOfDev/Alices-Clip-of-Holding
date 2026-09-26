"""Low-level Ctrl+V interception for the paste picker.

A WH_KEYBOARD_LL hook runs on a daemon thread and posts events onto a
queue that the Tk main loop drains. Synthetic keystrokes we inject to
perform the actual paste are tagged so they do not re-open the picker.
"""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
from ctypes import wintypes
from enum import Enum

LOGGER = logging.getLogger(__name__)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_V = 0x56
LLKHF_INJECTED = 0x10

HC_ACTION = 0


class HotkeyEvent(str, Enum):
    """Events the hook posts to the UI thread."""

    OPEN_PICKER = "open_picker"
    NATIVE_PASTE = "native_paste"


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Layout of ``KBDLLHOOKSTRUCT`` from Winuser.h."""

    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LOW_LEVEL_KEYBOARD_PROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


def _user32():
    """Return user32 only when ctypes exposes windll."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise RuntimeError("ctypes.windll is only available on Windows.")
    return windll.user32


class HotkeyHook:
    """Installs and tears down the process-wide Ctrl+V hook."""

    def __init__(self, intercept_ctrl_v: bool, allow_native_ctrl_shift_v: bool) -> None:
        """Create the hook object. Call ``start`` to install it.

        Args:
            intercept_ctrl_v: When True, Ctrl+V is swallowed and posted
                as ``OPEN_PICKER``.
            allow_native_ctrl_shift_v: When True, Ctrl+Shift+V is posted
                as ``NATIVE_PASTE`` instead of opening the picker.
        """
        self.intercept_ctrl_v = intercept_ctrl_v
        self.allow_native_ctrl_shift_v = allow_native_ctrl_shift_v
        self.events: queue.Queue[HotkeyEvent] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._hook_id = None
        self._proc = None
        self._user32 = _user32()
        self._suppress_injected = False
        self._stop = threading.Event()

    def start(self) -> None:
        """Start the hook thread and message pump."""
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="alice-hotkeys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the hook thread to unhook and exit."""
        self._stop.set()
        self._user32.PostThreadMessageW(
            ctypes.c_ulong(self._thread.ident) if self._thread and self._thread.ident else 0,
            0x0012,
            0,
            0,
        )

    def begin_injected_paste(self) -> None:
        """Ignore hook events until ``end_injected_paste`` is called."""
        self._suppress_injected = True

    def end_injected_paste(self) -> None:
        """Resume intercepting Ctrl+V after a synthetic paste."""
        self._suppress_injected = False

    def drain(self) -> list[HotkeyEvent]:
        """Pop every pending event. Called from the Tk main loop."""
        items: list[HotkeyEvent] = []
        while True:
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                return items

    def _run(self) -> None:
        """Install the hook and pump messages until stop is requested."""
        self._proc = LOW_LEVEL_KEYBOARD_PROC(self._callback)
        self._hook_id = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._proc,
            ctypes.c_void_p(0),
            0,
        )
        if not self._hook_id:
            LOGGER.error("SetWindowsHookExW failed with %s", ctypes.GetLastError())
            return
        msg = wintypes.MSG()
        while not self._stop.is_set():
            result = self._user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if result == 0 or result == -1:
                break
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))
        if self._hook_id:
            self._user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

    def _callback(self, n_code: int, w_param: int, l_param: int) -> int:
        """Low-level keyboard procedure.

        Args:
            n_code: Hook code. We only inspect ``HC_ACTION``.
            w_param: Message id (keydown / syskeydown).
            l_param: Pointer to ``KBDLLHOOKSTRUCT``.

        Returns:
            1 to swallow the key, or the next hook's result to pass it on.
        """
        if n_code == HC_ACTION and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            injected = bool(info.flags & LLKHF_INJECTED)
            if (
                not injected
                and not self._suppress_injected
                and info.vkCode == VK_V
                and self._ctrl_down()
            ):
                if self.allow_native_ctrl_shift_v and self._shift_down():
                    self.events.put(HotkeyEvent.NATIVE_PASTE)
                    return int(self._user32.CallNextHookEx(self._hook_id, n_code, w_param, l_param))
                if self.intercept_ctrl_v:
                    self.events.put(HotkeyEvent.OPEN_PICKER)
                    return 1
        return int(self._user32.CallNextHookEx(self._hook_id, n_code, w_param, l_param))

    def _ctrl_down(self) -> bool:
        """Return True if either Control key is currently down."""
        return self._key_down(VK_CONTROL) or self._key_down(VK_LCONTROL) or self._key_down(VK_RCONTROL)

    def _shift_down(self) -> bool:
        """Return True if either Shift key is currently down."""
        return self._key_down(VK_SHIFT) or self._key_down(VK_LSHIFT) or self._key_down(VK_RSHIFT)

    def _key_down(self, vk: int) -> bool:
        """Return True if virtual-key ``vk`` is physically down."""
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)


def send_ctrl_v() -> None:
    """Inject Ctrl+V into the foreground window using ``SendInput``."""
    user32 = _user32()
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]

    def pack(vk: int, flags: int) -> INPUT:
        item = INPUT()
        item.type = INPUT_KEYBOARD
        item.union.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
        return item

    stroke = (INPUT * 4)(
        pack(VK_CONTROL, 0),
        pack(VK_V, 0),
        pack(VK_V, KEYEVENTF_KEYUP),
        pack(VK_CONTROL, KEYEVENTF_KEYUP),
    )
    sent = user32.SendInput(4, ctypes.byref(stroke), ctypes.sizeof(INPUT))
    if sent != 4:
        LOGGER.error("SendInput pasted %s of 4 events (err=%s)", sent, ctypes.GetLastError())

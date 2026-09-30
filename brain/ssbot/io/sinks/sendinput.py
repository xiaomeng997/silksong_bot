"""Keyboard output through Win32 SendInput with hardware scancodes.

Only reaches the foreground window, so callers must keep the game focused (see game_window.focus).
Every press is held for at least MIN_HOLD_S so the game's per-frame input poll sees both edges.
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MIN_HOLD_S = 0.021  # DESIGN.md C19: >= 21 ms on PC

# Scancode set 1; (code, extended). Default Silksong keyboard bindings (versions.lock key_bindings).
KEYS = {
    "jump": (0x2C, False),        # Z
    "attack": (0x2D, False),      # X
    "dash": (0x2E, False),        # C
    "bind": (0x1E, False),        # A
    "clawline": (0x1F, False),    # S
    "needolin": (0x20, False),    # D
    "quickcast": (0x21, False),   # F
    "taunt": (0x2F, False),       # V
    "inventory": (0x17, False),   # I
    "quickmap": (0x0F, False),    # Tab (never used in runs)
    "pause": (0x01, False),       # Esc
    "enter": (0x1C, False),
    "up": (0x48, True),
    "down": (0x50, True),
    "left": (0x4B, True),
    "right": (0x4D, True),
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _INPUTUNION(ctypes.Union):
    # MOUSEINPUT is the largest member; pad so sizeof(INPUT) matches the Win32 definition (40 bytes on x64).
    _fields_ = [("ki", KEYBDINPUT), ("_pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _event(name: str, up: bool) -> INPUT:
    code, extended = KEYS[name]
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if extended else 0) | (KEYEVENTF_KEYUP if up else 0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(0, code, flags, 0, 0)))


def send(changes: list[tuple[str, bool]]) -> None:
    """Send key transitions in one batch; each item is (key, down)."""
    if not changes:
        return
    arr = (INPUT * len(changes))(*(_event(k, up=not down) for k, down in changes))
    sent = user32.SendInput(len(changes), arr, ctypes.sizeof(INPUT))
    if sent != len(changes):
        raise ctypes.WinError(ctypes.get_last_error())


def tap(name: str, hold_s: float = MIN_HOLD_S) -> None:
    send([(name, True)])
    time.sleep(max(hold_s, MIN_HOLD_S))
    send([(name, False)])


def hold(name: str, seconds: float) -> None:
    tap(name, seconds)


def release_all() -> None:
    send([(k, False) for k in KEYS])

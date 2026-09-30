"""Find and focus the Silksong window."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
TITLE = "Hollow Knight Silksong"


def find() -> int:
    return user32.FindWindowW(None, TITLE)


def is_foreground(hwnd: int) -> bool:
    return hwnd != 0 and user32.GetForegroundWindow() == hwnd


def foreground() -> int:
    return user32.GetForegroundWindow()


def restore_foreground(prev: int) -> None:
    """Hand the foreground back to the window the user was in (e.g. the Claude app)."""
    if prev and prev != foreground():
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(prev)


def park_cursor_outside(hwnd: int) -> None:
    """Move the OS cursor just below the game window so hovering cannot change a menu selection."""
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    left, top, right, bottom = rect(hwnd)
    if left <= point.x < right and top <= point.y < bottom:
        user32.SetCursorPos(left + 20, bottom + 20)


def focus(hwnd: int) -> bool:
    """Bring the game to the foreground. Windows may refuse; the caller must check is_foreground."""
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    # Pressing and releasing Alt lets a background process take the foreground (foreground lock rule).
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return is_foreground(hwnd)


def rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom

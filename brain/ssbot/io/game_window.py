"""Find and focus the Silksong window."""
import ctypes
import time
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


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetWindowThreadProcessId.restype = wintypes.DWORD


def focus(hwnd: int, attempts: int = 5) -> bool:
    """Bring the game to the foreground and confirm it. Returns False if Windows refused every attempt;
    callers must never send keys in that case, or the keys land in whatever window the user is in."""
    SW_RESTORE = 9
    for _ in range(attempts):
        if is_foreground(hwnd):
            return True
        user32.ShowWindow(hwnd, SW_RESTORE)
        # Windows only lets the process that owns the foreground (or received the last input) change it.
        # Temporarily sharing the foreground thread's input state satisfies that rule.
        fg = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        me = kernel32.GetCurrentThreadId()
        attached = bool(fg_thread) and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True)
        try:
            user32.keybd_event(0x12, 0, 0, 0)  # Alt tap: also unlocks SetForegroundWindow
            user32.keybd_event(0x12, 0, 2, 0)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(me, fg_thread, False)
        for _ in range(10):
            if is_foreground(hwnd):
                return True
            time.sleep(0.02)
    return False


def rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


_DWMWA_EXTENDED_FRAME_BOUNDS = 9


def client_in_capture(hwnd: int) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the client area (the game image) inside a Windows Graphics Capture frame of the window.
    WGC captures the visible frame (DWM extended frame bounds, which excludes the invisible resize borders that
    GetWindowRect includes), so the offset is ClientToScreen(0, 0) minus that frame's origin."""
    frame = wintypes.RECT()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), _DWMWA_EXTENDED_FRAME_BOUNDS,
                                                   ctypes.byref(frame), ctypes.sizeof(frame))
    if hr != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(frame))
    origin = _Point(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    client = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client))
    return origin.x - frame.left, origin.y - frame.top, client.right - client.left, client.bottom - client.top

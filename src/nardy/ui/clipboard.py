"""Reliable clipboard access.

pygame.scrap is flaky on Windows (needs a live window handle bound at the
right init order, often just returns None), so on Windows we talk to the
Win32 clipboard directly via ctypes — no extra dependency, no window-handle
dance.
"""

from __future__ import annotations

import sys

_IS_WINDOWS = sys.platform == "win32"

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _win32_apis():
    """Return (user32, kernel32) with correct 64-bit-safe signatures."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL

    return user32, kernel32


def get_text() -> str | None:
    """Return clipboard text, or None if unavailable/empty."""
    if _IS_WINDOWS:
        return _win32_get_text()
    return _scrap_get_text()


def set_text(text: str) -> bool:
    """Copy text to the clipboard. Returns True on success."""
    if _IS_WINDOWS:
        return _win32_set_text(text)
    return _scrap_set_text(text)


def _win32_get_text() -> str | None:
    import ctypes

    try:
        user32, kernel32 = _win32_apis()
    except Exception:
        return None

    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return None
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _win32_set_text(text: str) -> bool:
    import ctypes

    try:
        user32, kernel32 = _win32_apis()
    except Exception:
        return False

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return False
        try:
            ctypes.memmove(locked, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
        return True
    finally:
        user32.CloseClipboard()


def _scrap_get_text() -> str | None:
    try:
        import pygame.scrap
        if not pygame.scrap.get_init():
            return None
        data = pygame.scrap.get(pygame.SCRAP_TEXT)
        if not data:
            return None
        return data.decode("utf-8", errors="ignore").rstrip("\x00")
    except Exception:
        return None


def _scrap_set_text(text: str) -> bool:
    try:
        import pygame.scrap
        if not pygame.scrap.get_init():
            return False
        pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
        return True
    except Exception:
        return False

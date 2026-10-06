"""Checks the Windows scan code table against Windows itself (runs only on Windows)."""

import sys

import pytest

from keyboard import SUPPORTED_KEYS, WINDOWS_SCANCODES

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows")

VIRTUAL_KEYS = {
    **{c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0xA0, "escape": 0x1B, "space": 0x20,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}
MAPVK_VK_TO_VSC_EX = 4


def test_every_key_has_a_scan_code():
    assert set(WINDOWS_SCANCODES) == SUPPORTED_KEYS


@pytest.mark.parametrize("key", sorted(SUPPORTED_KEYS))
def test_scan_code_matches_windows(key):
    import ctypes

    code = ctypes.windll.user32.MapVirtualKeyW(VIRTUAL_KEYS[key], MAPVK_VK_TO_VSC_EX)
    scan, extended = WINDOWS_SCANCODES[key]
    assert code & 0xFF == scan
    # Windows reports the arrows without their E0 prefix (they share codes with the keypad),
    # so the extended flag is checked by tests/check_real_keys.py: ArrowUp, not Numpad8.
    assert extended == (key in ("up", "down", "left", "right"))

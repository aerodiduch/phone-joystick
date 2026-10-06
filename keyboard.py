"""Synthetic key presses on macOS (Quartz CGEvent) and Windows (SendInput)."""

import logging
import sys

log = logging.getLogger("joystick.keyboard")

# macOS virtual key codes (kVK_* from HIToolbox/Events.h).
MAC_KEYCODES: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26,
    "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35, "enter": 36,
    "l": 37, "j": 38, "k": 40, "n": 45, "m": 46, "tab": 48, "space": 49,
    "backspace": 51, "escape": 53, "shift": 56,
    "left": 123, "right": 124, "down": 125, "up": 126,
}

# Windows set-1 scan codes and whether they need the extended (E0) flag. Scan codes,
# not virtual keys, so games that read raw input see them too.
WINDOWS_SCANCODES: dict[str, tuple[int, bool]] = {
    **{k: (v, False) for k, v in {
        "escape": 0x01, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07,
        "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B, "backspace": 0x0E, "tab": 0x0F,
        "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15, "u": 0x16,
        "i": 0x17, "o": 0x18, "p": 0x19, "enter": 0x1C, "a": 0x1E, "s": 0x1F, "d": 0x20,
        "f": 0x21, "g": 0x22, "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26, "shift": 0x2A,
        "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
        "space": 0x39,
    }.items()},
    "up": (0x48, True), "left": (0x4B, True), "right": (0x4D, True), "down": (0x50, True),
}

# Only these keys can be mapped, so a phone can never send Cmd/Ctrl/Alt combos.
SUPPORTED_KEYS = frozenset(MAC_KEYCODES)
MODIFIER_FLAGS: dict[str, int] = {"shift": 0x00020000}  # kCGEventFlagMaskShift


def accessibility_trusted(prompt: bool) -> bool:
    """macOS only: whether this process may post keyboard events (Accessibility permission)."""
    import HIServices

    options = {HIServices.kAXTrustedCheckOptionPrompt: prompt}
    return bool(HIServices.AXIsProcessTrustedWithOptions(options))


class MacKeyboard:
    """Posts key down/up events to the frontmost app."""

    def __init__(self) -> None:
        import Quartz

        self._q = Quartz
        self._source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        self._flags = 0

    def _post(self, key: str, down: bool) -> None:
        q = self._q
        if key in MODIFIER_FLAGS:
            if down:
                self._flags |= MODIFIER_FLAGS[key]
            else:
                self._flags &= ~MODIFIER_FLAGS[key]
        event = q.CGEventCreateKeyboardEvent(self._source, MAC_KEYCODES[key], down)
        q.CGEventSetFlags(event, self._flags)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def press(self, key: str) -> None:
        self._post(key, True)

    def release(self, key: str) -> None:
        self._post(key, False)


class WindowsKeyboard:
    """Sends key down/up events to the foreground window with SendInput."""

    KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        ulong_ptr = ctypes.c_size_t

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class MOUSEINPUT(ctypes.Structure):  # only here so the union has the right size
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ulong_ptr)]

        class INPUTUNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]

        self._ctypes = ctypes
        self._INPUT, self._KEYBDINPUT, self._INPUTUNION = INPUT, KEYBDINPUT, INPUTUNION
        self._send_input = ctypes.windll.user32.SendInput

    def _send(self, key: str, down: bool) -> None:
        scan, extended = WINDOWS_SCANCODES[key]
        flags = self.KEYEVENTF_SCANCODE
        if extended:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        if not down:
            flags |= self.KEYEVENTF_KEYUP
        event = self._INPUT(type=1, u=self._INPUTUNION(ki=self._KEYBDINPUT(0, scan, flags, 0, 0)))
        if self._send_input(1, self._ctypes.byref(event), self._ctypes.sizeof(event)) != 1:
            # Blocked when the foreground app runs as administrator and we don't.
            log.warning("Windows rejected the %s key (is the game running as administrator?)", key)

    def press(self, key: str) -> None:
        self._send(key, True)

    def release(self, key: str) -> None:
        self._send(key, False)


class DryRunKeyboard:
    """Records events instead of posting them (tests and --dry-run)."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def press(self, key: str) -> None:
        self.events.append(("down", key))
        log.info("down %s", key)

    def release(self, key: str) -> None:
        self.events.append(("up", key))
        log.info("up   %s", key)


def system_keyboard():
    if sys.platform == "darwin":
        return MacKeyboard()
    if sys.platform == "win32":
        return WindowsKeyboard()
    raise SystemExit("Only macOS and Windows are supported for now.")

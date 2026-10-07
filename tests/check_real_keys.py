"""Real key presses, end to end (macOS and Windows): uv run python tests/check_real_keys.py

1. Every supported key is sent to a visible test browser window, which reports the
   KeyboardEvent.code it got. This is what validates the key code tables.
2. Full chain: a headless "phone" page touches the stick and a button, the server sends
   real keys, and the visible window receives them.

It types into whatever window is in front, so run it only on a computer nobody is using.
It refuses to start if the mouse moved in the last few seconds (macOS) and stops
before any key if the test window is not in front.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402
from keyboard import SUPPORTED_KEYS, accessibility_trusted, system_keyboard  # noqa: E402

TEST_BUNDLE = "com.google.chrome.for.testing"
TOKEN = "real-keys"

EXPECTED_CODE = {
    **{c: f"Key{c.upper()}" for c in "abcdefghijklmnopqrstuvwxyz"},
    **{d: f"Digit{d}" for d in "0123456789"},
    "enter": "Enter", "tab": "Tab", "space": "Space", "escape": "Escape", "shift": "ShiftLeft",
    "backspace": "Backspace",
    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
}

GAME_PAGE = """<!doctype html><title>Key test</title><body style="font:20px system-ui">
<p>Key test: hands off the keyboard.</p><pre id="log"></pre>
<script>
  window.events = [];
  for (const type of ["keydown", "keyup"]) {
    window.addEventListener(type, (e) => {
      e.preventDefault();
      window.events.push({ type, code: e.code, key: e.key, shift: e.shiftKey, repeat: e.repeat });
      document.getElementById("log").textContent += `${type} ${e.code} ${e.key}\\n`;
    }, true);
  }
</script>"""


def frontmost() -> str:
    """Bundle id of the frontmost app (macOS) or title of the foreground window (Windows)."""
    if sys.platform == "win32":
        import ctypes

        user32 = ctypes.windll.user32
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(user32.GetForegroundWindow(), buffer, 256)
        return buffer.value
    asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True).stdout.strip()
    out = subprocess.run(["lsappinfo", "info", "-only", "bundleid", asn], capture_output=True, text=True).stdout
    return out.split("=")[-1].strip().strip('"')


def test_window_in_front() -> bool:
    front = frontmost()
    return front.startswith("Key test") if sys.platform == "win32" else front == TEST_BUNDLE


def require_focus() -> None:
    if not test_window_in_front():
        raise SystemExit(f"ABORT: {frontmost()!r} is in front, not the test window. No more keys sent.")


def require_idle_mac() -> None:
    if sys.platform != "darwin":
        return
    import Quartz

    idle = min(Quartz.CGEventSourceSecondsSinceLastEventType(Quartz.kCGEventSourceStateHIDSystemState, kind)
               for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown))
    if idle < 5:
        raise SystemExit("ABORT: someone is using this Mac (mouse moved in the last 5 s). Nothing sent.")


async def focus_window(page) -> None:
    await page.bring_to_front()
    for _ in range(20):
        if test_window_in_front():
            break
        if sys.platform == "darwin":
            subprocess.run(["open", "-b", TEST_BUNDLE])
        await asyncio.sleep(0.25)
    require_focus()
    await page.click("body")


async def events(page) -> list[dict]:
    await asyncio.sleep(0.15)
    return await page.evaluate("window.events.splice(0)")


async def check_keycodes(page, kb) -> list[str]:
    failures = []
    for key in sorted(SUPPORTED_KEYS):
        require_focus()
        kb.press(key)
        kb.release(key)
        got = [(e["type"], e["code"]) for e in await events(page)]
        want = [("keydown", EXPECTED_CODE[key]), ("keyup", EXPECTED_CODE[key])]
        if got != want:
            failures.append(f"{key}: got {got}, want {want}")
    # Shift held while another key goes down.
    require_focus()
    kb.press("shift"); kb.press("a"); kb.release("a"); kb.release("shift")
    got = [(e["type"], e["key"], e["shift"]) for e in await events(page)]
    want = [("keydown", "Shift", True), ("keydown", "A", True), ("keyup", "A", True), ("keyup", "Shift", False)]
    if got != want:
        failures.append(f"shift+a: got {got}, want {want}")
    return failures


async def check_full_chain(p, page, kb) -> list[str]:
    from aiohttp.test_utils import TestServer

    layouts, _ = server.load_layouts(server.DEFAULT_LAYOUTS_FILE)
    state = Path(__file__).resolve().parent / ".real-keys-state.json"
    app = server.create_app(kb, layouts, "arrows", TOKEN, state_path=state)
    srv = TestServer(app, port=0)
    await srv.start_server()
    failures = []
    phone_browser = await p.chromium.launch()  # headless: never takes focus
    try:
        ctx = await phone_browser.new_context(viewport={"width": 852, "height": 393}, is_mobile=True, has_touch=True)
        phone = await ctx.new_page()
        await phone.goto(f"http://127.0.0.1:{srv.port}/?k={TOKEN}")
        await phone.wait_for_function("document.getElementById('status').dataset.state === 'on'")
        cdp = await ctx.new_cdp_session(phone)

        async def touch(kind, pts):
            await cdp.send("Input.dispatchTouchEvent", {
                "type": kind, "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in pts.items()]})

        z = await phone.locator("#dpad").bounding_box()  # the phone starts on the d-pad
        a = await phone.locator(".btn.a").bounding_box()
        sx, sy = z["x"] + z["width"] / 2, z["y"] + z["height"] / 2
        ax, ay = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2

        await focus_window(page)
        await events(page)
        await touch("touchStart", {1: (sx, sy)})
        await touch("touchMove", {1: (sx, sy - 55)})
        require_focus()
        await touch("touchStart", {1: (sx, sy - 55), 2: (ax, ay)})
        await asyncio.sleep(0.4)  # held: a game would see both keys down
        require_focus()
        await touch("touchEnd", {})
        got = [(e["type"], e["code"]) for e in await events(page) if not e["repeat"]]
        want = [("keydown", "ArrowUp"), ("keydown", "Space"), ("keyup", "ArrowUp"), ("keyup", "Space")]
        if sorted(got[:2]) != sorted(want[:2]) or sorted(got[2:]) != sorted(want[2:]):
            failures.append(f"phone -> keys: got {got}, want {want}")
        if app[server.HUB].held:
            failures.append(f"keys still held: {app[server.HUB].held}")
    finally:
        await phone_browser.close()
        await srv.close()
        app[server.HUB].release_all()
        state.unlink(missing_ok=True)
    return failures


async def main() -> int:
    if sys.platform == "darwin" and not accessibility_trusted(prompt=False):
        print("Accessibility permission missing for this terminal.")
        return 1
    require_idle_mac()
    kb = system_keyboard()
    async with async_playwright() as p:
        game = await p.chromium.launch(headless=False, args=["--window-size=700,500"])
        try:
            page = await game.new_page()
            await page.set_content(GAME_PAGE)
            await focus_window(page)
            failures = await check_keycodes(page, kb)
            print(f"keycodes: {len(SUPPORTED_KEYS)} keys + shift combo, {len(failures)} failures")
            chain = await check_full_chain(p, page, kb)
            print(f"full chain phone -> server -> keys: {'OK' if not chain else 'FAIL'}")
            failures += chain
        finally:
            for key in SUPPORTED_KEYS:  # nothing stays down, whatever happened
                kb.release(key)
            await game.close()
    for f in failures:
        print("FAIL", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

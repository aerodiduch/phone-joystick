"""Serves the phone controller page and turns its input into key presses on this computer."""

import argparse
import asyncio
import atexit
import json
import locale
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import WSCloseCode, WSMsgType, web

from keyboard import MODIFIER_FLAGS, SUPPORTED_KEYS, DryRunKeyboard, accessibility_trusted, system_keyboard

APP_NAME = "phone-joystick"
FROZEN = getattr(sys, "frozen", False)  # running as the PyInstaller .exe
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC_DIR = ROOT / "static"


def user_dir() -> Path:
    """Next to the code when run from source; in the user's profile for the .exe,
    which may sit in a folder it can't write to."""
    if not FROZEN:
        return ROOT
    path = Path(os.environ.get("APPDATA") or Path.home() / ".config") / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


USER_DIR = user_dir()
STATE_FILE = USER_DIR / "state.json"
LAYOUTS_FILE = USER_DIR / "layouts.json" if (USER_DIR / "layouts.json").exists() else ROOT / "layouts.json"

CONTROLS = ("up", "down", "left", "right", "a", "b", "x", "y", "l1", "r1", "start", "select")
PING_TIMEOUT = 1.5  # seconds of silence before a phone's keys are released
BUILD = str(time.time_ns())  # a page from an older server run reloads itself
# Shortest time a key stays down. Wi-Fi can deliver a quick tap's press and release together,
# and a game that reads the keyboard once per frame would miss it (AutoHotkey's SetKeyDelay
# has a PressDuration setting for the same reason).
MIN_HOLD = 0.06

log = logging.getLogger("joystick")


def load_layouts(path: Path) -> tuple[dict, str]:
    data = json.loads(path.read_text())
    layouts = data["layouts"]
    # A layout maps any subset of CONTROLS; the phone hides the controls it leaves out.
    for name, layout in layouts.items():
        keys = layout["keys"]
        unknown = sorted(set(keys) - set(CONTROLS))
        unsupported = sorted({k for k in keys.values() if k not in SUPPORTED_KEYS})
        if layout.get("stickSprint") and layout["stickSprint"] not in keys:
            unknown.append(layout["stickSprint"])
        if unknown or unsupported:
            raise ValueError(f"layout {name!r}: unknown controls {unknown}, unsupported keys {unsupported}")
    default = data.get("default") or next(iter(layouts))
    return layouts, default


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2) + "\n")


@dataclass
class Phone:
    ws: web.WebSocketResponse
    pressed: set[str] = field(default_factory=set)
    last_seen: float = field(default_factory=time.monotonic)


class Hub:
    """Tracks what every connected phone is pressing and keeps the computer's keys in sync."""

    def __init__(self, keyboard, layouts: dict, layout: str, min_hold: float = MIN_HOLD) -> None:
        self.keyboard = keyboard
        self.layouts = layouts
        self.layout = layout
        self.min_hold = min_hold
        self.phones: list[Phone] = []
        self.held: set[str] = set()
        self.down_at: dict[str, float] = {}
        self.pending: dict[str, asyncio.TimerHandle] = {}  # releases waiting for MIN_HOLD

    def sync(self) -> None:
        keymap = self.layouts[self.layout]["keys"]
        wanted = {keymap[c] for phone in self.phones for c in phone.pressed if c in keymap}
        now = time.monotonic()
        released = self.held - wanted
        waits = {key: self.min_hold - (now - self.down_at[key]) for key in released}
        # Modifiers go down first and come up last, also when a release is delayed.
        longest = max((w for k, w in waits.items() if k not in MODIFIER_FLAGS), default=0)
        for key in sorted(released, key=lambda k: k in MODIFIER_FLAGS):
            wait = max(waits[key], longest) if key in MODIFIER_FLAGS else waits[key]
            if wait > 0:
                self.pending[key] = asyncio.get_running_loop().call_later(wait, self._release, key)
            else:
                self._release(key)
        for key in sorted(wanted - self.held, key=lambda k: k not in MODIFIER_FLAGS):
            if key in self.pending:  # pressed again before its delayed release: it never went up
                self.pending.pop(key).cancel()
            else:
                self.keyboard.press(key)
                self.down_at[key] = now
                log.debug("down %s", key)
        self.held = wanted

    def _release(self, key: str) -> None:
        self.pending.pop(key, None)
        held_ms = (time.monotonic() - self.down_at.pop(key)) * 1000
        self.keyboard.release(key)
        log.debug("up   %s  %.0f ms", key, held_ms)

    def release_all(self) -> None:
        """Lets go of every key right away (shutdown, exit)."""
        for phone in self.phones:
            phone.pressed.clear()
        for key, timer in list(self.pending.items()):
            timer.cancel()
            self._release(key)
        for key in sorted(self.held, key=lambda k: k in MODIFIER_FLAGS):
            self._release(key)
        self.held = set()

    def config_message(self) -> dict:
        current = self.layouts[self.layout]
        return {
            "type": "config",
            "build": BUILD,
            "layout": self.layout,
            "layouts": [{"id": name, "label": layout["label"]} for name, layout in self.layouts.items()],
            "keys": current["keys"],
            "names": current.get("names", {}),
            "style": current.get("style", ""),
            "stickSprint": current.get("stickSprint", ""),
        }


HUB = web.AppKey("hub", Hub)
TOKEN = web.AppKey("token", str)
STATE_PATH = web.AppKey("state_path", Path)
TIMEOUT = web.AppKey("timeout", float)


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def websocket(request: web.Request) -> web.WebSocketResponse:
    if not secrets.compare_digest(request.query.get("k", ""), request.app[TOKEN]):
        raise web.HTTPForbidden()
    hub = request.app[HUB]
    ws = web.WebSocketResponse(heartbeat=2.0)
    await ws.prepare(request)
    sock = request.transport.get_extra_info("socket") if request.transport else None
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    phone = Phone(ws)
    hub.phones.append(phone)
    log.info(TEXT["connected"], request.remote)
    await ws.send_json(hub.config_message())
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            gap = time.monotonic() - phone.last_seen
            if gap > 0.8:
                log.debug("%.0f ms without messages from the phone", gap * 1000)
            phone.last_seen = time.monotonic()
            try:
                data = json.loads(msg.data)
            except ValueError:
                continue
            kind = data.get("type")
            if kind == "state" and isinstance(data.get("pressed"), list):
                phone.pressed = {c for c in data["pressed"] if c in CONTROLS}
                hub.sync()
            elif kind == "layout" and data.get("name") in hub.layouts and data["name"] != hub.layout:
                hub.layout = data["name"]
                hub.sync()
                state_path = request.app[STATE_PATH]
                save_state(state_path, {**load_state(state_path), "layout": hub.layout})
                log.info(TEXT["layout"], hub.layouts[hub.layout]["label"])
                config = hub.config_message()
                for other in hub.phones:
                    if not other.ws.closed:
                        await other.ws.send_json(config)
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    finally:
        hub.phones.remove(phone)
        hub.sync()
        log.info(TEXT["disconnected"], request.remote)
    return ws


async def watchdog(app: web.Application):
    """Releases the keys of a phone that went silent (screen locked, Wi-Fi dropped)."""

    async def loop() -> None:
        hub, timeout = app[HUB], app[TIMEOUT]
        while True:
            await asyncio.sleep(0.25)
            now = time.monotonic()
            for phone in list(hub.phones):
                if now - phone.last_seen > timeout and not phone.ws.closed:
                    log.warning(TEXT["silent"])
                    phone.pressed.clear()
                    hub.sync()
                    asyncio.create_task(phone.ws.close(code=WSCloseCode.GOING_AWAY))

    task = asyncio.create_task(loop())
    yield
    task.cancel()


async def on_shutdown(app: web.Application) -> None:
    hub = app[HUB]
    hub.release_all()
    for phone in list(hub.phones):
        await phone.ws.close(code=WSCloseCode.GOING_AWAY)


async def no_cache(request: web.Request, response: web.StreamResponse) -> None:
    response.headers["Cache-Control"] = "no-store"


def create_app(keyboard, layouts: dict, layout: str, token: str, state_path: Path = STATE_FILE,
               timeout: float = PING_TIMEOUT, min_hold: float = MIN_HOLD) -> web.Application:
    app = web.Application()
    app[HUB] = Hub(keyboard, layouts, layout, min_hold)
    app[TOKEN] = token
    app[STATE_PATH] = state_path
    app[TIMEOUT] = timeout
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket)
    app.router.add_static("/static", STATIC_DIR)
    app.cleanup_ctx.append(watchdog)
    app.on_shutdown.append(on_shutdown)
    app.on_response_prepare.append(no_cache)
    return app


def lan_address() -> str:
    if sys.platform == "darwin":  # Wi-Fi first: with a VPN up, the default route is the tunnel
        for iface in ("en0", "en1"):
            result = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True)
            if result.stdout.strip():
                return result.stdout.strip()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # no packet is sent; it only picks the outgoing interface
            return probe.getsockname()[0]
        except OSError:
            return socket.gethostname()


def spanish() -> bool:
    lang = os.environ.get("LANG") or ""
    if not lang:
        try:
            lang = locale.getlocale()[0] or ""
        except ValueError:
            pass
    return lang.lower().startswith(("es", "spanish"))


MESSAGES = {
    "es": {
        "description": "Usá el teléfono como joystick para jugar en la computadora.",
        "dry_run": "no aprieta teclas, solo las muestra",
        "verbose": "muestra cada tecla y cuánto duró apretada",
        "accessibility": "Falta el permiso de Accesibilidad para esta app.\n"
                         "Activalo en Ajustes del Sistema → Privacidad y seguridad → Accesibilidad. "
                         "Espero acá; sigue solo cuando lo actives.",
        "scan": "Escaneá el código con la cámara del teléfono (misma red Wi-Fi que esta computadora):",
        "ready": "Dejá el juego en primer plano. Ctrl+C para salir.",
        "connected": "Teléfono conectado (%s)",
        "disconnected": "Teléfono desconectado (%s)",
        "silent": "El teléfono dejó de responder: suelto sus teclas",
        "layout": "Teclas: %s",
    },
    "en": {
        "description": "Use your phone as a joystick to play on this computer.",
        "dry_run": "don't press keys, just print them",
        "verbose": "print every key and how long it was held",
        "accessibility": "This app needs the Accessibility permission.\n"
                         "Turn it on in System Settings → Privacy & Security → Accessibility. "
                         "Waiting here; it carries on as soon as you do.",
        "scan": "Scan the code with your phone's camera (same Wi-Fi network as this computer):",
        "ready": "Keep the game in the foreground. Ctrl+C to quit.",
        "connected": "Phone connected (%s)",
        "disconnected": "Phone disconnected (%s)",
        "silent": "The phone stopped responding: releasing its keys",
        "layout": "Keys: %s",
    },
}
TEXT = MESSAGES["en"]


def print_qr(url: str) -> None:
    import qrcode

    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def main() -> None:
    global TEXT
    TEXT = text = MESSAGES["es" if spanish() else "en"]
    parser = argparse.ArgumentParser(description=text["description"])
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--dry-run", action="store_true", help=text["dry_run"])
    parser.add_argument("--verbose", action="store_true", help=text["verbose"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S")
    if args.verbose:
        log.setLevel(logging.DEBUG)

    if args.dry_run:
        keyboard = DryRunKeyboard()
    else:
        if sys.platform == "darwin" and not accessibility_trusted(prompt=True):
            print(text["accessibility"], flush=True)
            while not accessibility_trusted(prompt=False):
                time.sleep(1)
        keyboard = system_keyboard()

    layouts, default = load_layouts(LAYOUTS_FILE)
    state = load_state(STATE_FILE)
    if "token" not in state:
        state["token"] = secrets.token_urlsafe(8)
        save_state(STATE_FILE, state)
    layout = state["layout"] if state.get("layout") in layouts else default

    app = create_app(keyboard, layouts, layout, state["token"])
    atexit.register(app[HUB].release_all)

    url = f"http://{lan_address()}:{args.port}/?k={state['token']}"
    print(f"\n{text['scan']}\n")
    print_qr(url)
    print(f"{url}\n\n{text['ready']}\n", flush=True)
    web.run_app(app, port=args.port, print=None, access_log=None)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the QR uses block characters
    try:
        main()
    except Exception:
        if not FROZEN:
            raise
        # Double-clicked .exe: keep the window open so the error can be read.
        import traceback

        traceback.print_exc()
        input("\nEnter ↵")

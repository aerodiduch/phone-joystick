"""Serves the phone controller page and turns its input into key presses on this computer."""

import argparse
import asyncio
import atexit
import json
import locale
import logging
import os
import re
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
DEFAULT_LAYOUTS_FILE = ROOT / "layouts.json"   # shipped profiles, never written
PROFILES_FILE = USER_DIR / "profiles.json"     # the user's profiles, saved by /setup

CONTROLS = ("up", "down", "left", "right", "a", "b", "x", "y", "l1", "r1", "start", "select")
PING_TIMEOUT = 1.5  # seconds of silence before a phone's keys are released
BUILD = str(time.time_ns())  # a page from an older server run reloads itself
# Shortest time a key stays down. Wi-Fi can deliver a quick tap's press and release together,
# and a game that reads the keyboard once per frame would miss it (AutoHotkey's SetKeyDelay
# has a PressDuration setting for the same reason).
MIN_HOLD = 0.06

log = logging.getLogger("joystick")


PROFILE_ID = re.compile(r"[a-z0-9_-]{1,40}")
STYLES = ("", "playstation")


def check_layouts(layouts) -> None:
    """Raises ValueError if the layouts can't be used. A layout maps any subset of
    CONTROLS; the phone hides the controls it leaves out."""
    if not isinstance(layouts, dict) or not layouts:
        raise ValueError("there must be at least one layout")
    for name, layout in layouts.items():
        if not PROFILE_ID.fullmatch(str(name)) or not isinstance(layout, dict):
            raise ValueError(f"bad layout id {name!r}")
        label = layout.get("label")
        if not isinstance(label, str) or not label.strip() or len(label) > 40:
            raise ValueError(f"layout {name!r}: the name must have 1 to 40 characters")
        keys, names = layout.get("keys"), layout.get("names", {})
        if not isinstance(keys, dict) or not isinstance(names, dict):
            raise ValueError(f"layout {name!r}: keys and names must be objects")
        unknown = sorted(set(keys) - set(CONTROLS)) + sorted(set(names) - set(CONTROLS))
        unsupported = sorted(str(k) for k in keys.values() if k not in SUPPORTED_KEYS)
        if any(not isinstance(v, str) or len(v) > 3 for v in names.values()):
            unsupported.append("names")
        if layout.get("style", "") not in STYLES:
            unsupported.append("style")
        if layout.get("stickSprint") and layout["stickSprint"] not in keys:
            unknown.append(layout["stickSprint"])
        if unknown or unsupported:
            raise ValueError(f"layout {name!r}: unknown controls {unknown}, unsupported values {unsupported}")


def load_layouts(path: Path) -> tuple[dict, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    layouts = data["layouts"]
    check_layouts(layouts)
    default = data.get("default")
    return layouts, default if default in layouts else next(iter(layouts))


def load_profiles(path: Path = PROFILES_FILE) -> tuple[dict, str]:
    """The user's profiles; the shipped ones if there are none yet or the file is broken.
    The .exe from v0.2.0 told people to edit %APPDATA%\\phone-joystick\\layouts.json, so that is read too."""
    for candidate in [path] + ([USER_DIR / "layouts.json"] if FROZEN else []):
        if candidate.exists():
            try:
                return load_layouts(candidate)
            except (ValueError, KeyError, TypeError) as error:
                log.warning(TEXT["bad_profiles"], candidate, error)
    return load_layouts(DEFAULT_LAYOUTS_FILE)


def save_layouts(path: Path, layouts: dict, default: str) -> None:
    data = {"default": default, "layouts": layouts}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


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
        self.lang = ""  # "" follows each device's language
        self.haptics = True
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
            "lang": self.lang,
            "haptics": self.haptics,
        }


HUB = web.AppKey("hub", Hub)
TOKEN = web.AppKey("token", str)
STATE_PATH = web.AppKey("state_path", Path)
PROFILES_PATH = web.AppKey("profiles_path", Path)
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
                await use_layout(request.app, data["name"])
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    finally:
        hub.phones.remove(phone)
        hub.sync()
        log.info(TEXT["disconnected"], request.remote)
    return ws


async def broadcast(app: web.Application) -> None:
    config = app[HUB].config_message()
    for phone in list(app[HUB].phones):
        if not phone.ws.closed:
            await phone.ws.send_json(config)


async def use_layout(app: web.Application, name: str) -> None:
    hub = app[HUB]
    hub.layout = name
    hub.sync()
    save_state(app[STATE_PATH], {**load_state(app[STATE_PATH]), "layout": name})
    log.info(TEXT["layout"], hub.layouts[name]["label"])
    await broadcast(app)


# The setup page changes what the phones press, so only this computer may open it. A web page
# could still post to localhost from the user's own browser: the Host check stops DNS rebinding
# and the custom header forces a CORS preflight that this server never answers.
LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def local_only(request: web.Request, api: bool = True) -> None:
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    if request.remote not in LOOPBACK or host not in LOCAL_HOSTS:
        raise web.HTTPForbidden(text="Open this page on the computer itself: http://localhost:<port>/setup")
    if api and request.headers.get("X-Phone-Joystick") != "setup":
        raise web.HTTPForbidden()


def profiles_payload(app: web.Application) -> dict:
    hub = app[HUB]
    return {"layouts": hub.layouts, "active": hub.layout, "controls": CONTROLS,
            "keys": sorted(SUPPORTED_KEYS), "phones": len(hub.phones), "lang": hub.lang,
            "haptics": hub.haptics}


async def save_profiles(app: web.Application, layouts: dict, active: str) -> None:
    hub = app[HUB]
    hub.layouts = layouts
    save_layouts(app[PROFILES_PATH], layouts, active)
    await use_layout(app, active)


async def setup_page(request: web.Request) -> web.FileResponse:
    local_only(request, api=False)
    return web.FileResponse(STATIC_DIR / "setup.html")


async def get_profiles(request: web.Request) -> web.Response:
    local_only(request)
    return web.json_response(profiles_payload(request.app))


async def put_profiles(request: web.Request) -> web.Response:
    local_only(request)
    try:
        data = await request.json()
        layouts, active = data["layouts"], data["active"]
        check_layouts(layouts)
        if active not in layouts:
            raise ValueError(f"unknown layout {active!r}")
    except (ValueError, KeyError, TypeError) as error:
        raise web.HTTPBadRequest(text=str(error))
    await save_profiles(request.app, layouts, active)
    return web.json_response(profiles_payload(request.app))


async def save_settings(request: web.Request) -> web.Response:
    """Language and vibration: one choice for every phone, kept in state.json."""
    local_only(request)
    try:
        data = await request.json()
        lang, haptics = data.get("lang"), data.get("haptics")
    except (ValueError, AttributeError):
        raise web.HTTPBadRequest()
    if lang is not None and lang not in ("", *MESSAGES) or haptics is not None and not isinstance(haptics, bool):
        raise web.HTTPBadRequest(text="lang must be es, pt, en or empty; haptics true or false")
    hub, state = request.app[HUB], load_state(request.app[STATE_PATH])
    if lang is not None:
        global TEXT
        TEXT = MESSAGES[lang or system_language()]
        hub.lang = state["lang"] = lang
    if haptics is not None:
        hub.haptics = state["haptics"] = haptics
    save_state(request.app[STATE_PATH], state)
    await broadcast(request.app)
    return web.json_response(profiles_payload(request.app))


async def reset_profiles(request: web.Request) -> web.Response:
    local_only(request)
    layouts, default = load_layouts(DEFAULT_LAYOUTS_FILE)
    active = request.app[HUB].layout if request.app[HUB].layout in layouts else default
    await save_profiles(request.app, layouts, active)
    return web.json_response(profiles_payload(request.app))


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
               timeout: float = PING_TIMEOUT, min_hold: float = MIN_HOLD,
               profiles_path: Path = PROFILES_FILE, lang: str = "", haptics: bool = True) -> web.Application:
    app = web.Application()
    app[HUB] = Hub(keyboard, layouts, layout, min_hold)
    app[HUB].lang, app[HUB].haptics = lang, haptics
    app[TOKEN] = token
    app[STATE_PATH] = state_path
    app[PROFILES_PATH] = profiles_path
    app[TIMEOUT] = timeout
    app.router.add_get("/", index)
    app.router.add_get("/ws", websocket)
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/api/profiles", get_profiles)
    app.router.add_put("/api/profiles", put_profiles)
    app.router.add_post("/api/profiles/reset", reset_profiles)
    app.router.add_post("/api/settings", save_settings)
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


def system_language() -> str:
    lang = os.environ.get("LANG") or ""
    if not lang:
        try:
            lang = locale.getlocale()[0] or ""
        except ValueError:
            pass
    lang = lang.lower()
    if lang.startswith(("es", "spanish")):
        return "es"
    if lang.startswith(("pt", "portuguese")):
        return "pt"
    return "en"


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
        "layout": "Perfil: %s",
        "setup": "Para elegir las teclas, abrí en esta computadora: http://localhost:%d/setup",
        "bad_profiles": "No pude leer los perfiles de %s (%s); uso los de fábrica",
    },
    "pt": {
        "description": "Use o celular como joystick para jogar no computador.",
        "dry_run": "não aperta teclas, só mostra",
        "verbose": "mostra cada tecla e quanto tempo ficou apertada",
        "accessibility": "Este app precisa da permissão de Acessibilidade.\n"
                         "Ative em Ajustes do Sistema → Privacidade e Segurança → Acessibilidade. "
                         "Fico esperando; continua sozinho quando você ativar.",
        "scan": "Escaneie o código com a câmera do celular (mesma rede Wi-Fi deste computador):",
        "ready": "Deixe o jogo em primeiro plano. Ctrl+C para sair.",
        "connected": "Celular conectado (%s)",
        "disconnected": "Celular desconectado (%s)",
        "silent": "O celular parou de responder: soltando as teclas dele",
        "layout": "Perfil: %s",
        "setup": "Para escolher as teclas, abra neste computador: http://localhost:%d/setup",
        "bad_profiles": "Não consegui ler os perfis de %s (%s); usando os originais",
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
        "layout": "Profile: %s",
        "setup": "To choose the keys, open this on this computer: http://localhost:%d/setup",
        "bad_profiles": "Couldn't read the profiles in %s (%s); using the built-in ones",
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
    state = load_state(STATE_FILE)
    lang = state.get("lang") if state.get("lang") in MESSAGES else ""
    TEXT = text = MESSAGES[lang or system_language()]
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

    layouts, default = load_profiles()
    if "token" not in state:
        state["token"] = secrets.token_urlsafe(8)
        save_state(STATE_FILE, state)
    layout = state["layout"] if state.get("layout") in layouts else default

    app = create_app(keyboard, layouts, layout, state["token"], lang=lang, haptics=state.get("haptics", True) is not False)
    atexit.register(app[HUB].release_all)

    url = f"http://{lan_address()}:{args.port}/?k={state['token']}"
    print(f"\n{text['scan']}\n")
    print_qr(url)
    print(f"{url}\n\n{text['ready']}\n{text['setup'] % args.port}\n", flush=True)
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

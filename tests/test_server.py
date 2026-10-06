"""Protocol tests: phone messages in, key down/up events out (no real key presses)."""

import asyncio
import json
from pathlib import Path

import pytest

import server
from keyboard import MAC_KEYCODES, SUPPORTED_KEYS, WINDOWS_SCANCODES, DryRunKeyboard

ROOT = Path(__file__).resolve().parent.parent
LAYOUTS, DEFAULT = server.load_layouts(ROOT / "layouts.json")
TOKEN = "test-token"


@pytest.fixture
def keyboard():
    return DryRunKeyboard()


@pytest.fixture
def state_path(tmp_path):
    return tmp_path / "state.json"


@pytest.fixture
async def client(aiohttp_client, keyboard, state_path):
    app = server.create_app(keyboard, LAYOUTS, "arrows", TOKEN, state_path=state_path, timeout=0.6, min_hold=0)
    return await aiohttp_client(app)


@pytest.fixture
async def held_client(aiohttp_client, keyboard, state_path):
    """Same server with the real minimum hold time."""
    app = server.create_app(keyboard, LAYOUTS, "arrows", TOKEN, state_path=state_path, timeout=5)
    return await aiohttp_client(app)


async def connect(client):
    ws = await client.ws_connect(f"/ws?k={TOKEN}", autoping=True)
    config = await ws.receive_json()
    assert config["type"] == "config"
    return ws, config


async def press(ws, *controls):
    await ws.send_json({"type": "state", "pressed": list(controls)})
    await asyncio.sleep(0.05)


def take(keyboard):
    events, keyboard.events[:] = list(keyboard.events), []
    return events


def test_every_key_works_on_mac_and_windows():
    assert set(MAC_KEYCODES) == set(WINDOWS_SCANCODES) == SUPPORTED_KEYS


def test_layouts_only_use_supported_keys():
    for layout in LAYOUTS.values():
        assert set(layout["keys"]) <= set(server.CONTROLS)
        assert all(key in SUPPORTED_KEYS for key in layout["keys"].values())


# Keyboard bindings exported from PES 6 Web (Controls > Save file): action index -> SDL
# scancode, in the order of KEYBOARD_ACTIONS in the game's js/bindings.js.
PES6_KEYBOARD = {"0": 82, "1": 79, "2": 81, "3": 80, "4": 27, "5": 7, "6": 4, "7": 26, "8": 44,
                 "9": 42, "10": 8, "11": 20, "12": 12, "13": 14, "14": 13, "15": 15, "16": 29, "17": 6}
PES6_ACTIONS = ["D-Pad Up", "D-Pad Right", "D-Pad Down", "D-Pad Left", "Cross (X)", "Circle", "Square",
                "Triangle", "Start", "Select", "R Trigger", "L Trigger", "Analog Up", "Analog Down",
                "Analog Left", "Analog Right", "L2 Trigger", "R2 Trigger"]
SDL_SCANCODES = {**{4 + i: chr(ord("a") + i) for i in range(26)}, 42: "backspace", 44: "space",
                 79: "right", 80: "left", 81: "down", 82: "up"}


def test_playstation_layout_matches_pes6_controls():
    game = {PES6_ACTIONS[int(i)]: SDL_SCANCODES[code] for i, code in PES6_KEYBOARD.items()}
    keys = LAYOUTS["playstation"]["keys"]
    assert keys["up"] == game["D-Pad Up"] and keys["down"] == game["D-Pad Down"]
    assert keys["left"] == game["D-Pad Left"] and keys["right"] == game["D-Pad Right"]
    names = LAYOUTS["playstation"]["names"]
    for control, symbol, action in [("a", "✕", "Cross (X)"), ("b", "○", "Circle"),
                                    ("x", "□", "Square"), ("y", "△", "Triangle")]:
        assert names[control] == symbol
        assert keys[control] == game[action], (control, action)
    assert keys["l1"] == game["L Trigger"] and keys["r1"] == game["R Trigger"]
    assert keys["start"] == game["Start"] and keys["select"] == game["Select"]


async def test_rejects_missing_or_wrong_token(client):
    assert (await client.get("/ws")).status == 403
    assert (await client.get("/ws?k=nope")).status == 403


async def test_serves_page(client):
    resp = await client.get("/")
    assert resp.status == 200
    assert "nipplejs" in await resp.text()
    assert (await client.get("/static/app.js")).status == 200


async def test_config_has_labels_and_layouts(client):
    ws, config = await connect(client)
    assert config["layout"] == "arrows"
    assert [l["id"] for l in config["layouts"]] == ["arrows", "wasd", "playstation"]
    assert "l1" not in config["keys"] and config["style"] == "" and config["build"]
    assert config["keys"]["a"] == "space"
    assert config["keys"]["up"] == "up"
    assert config["keys"]["b"] == "z"
    await ws.close()


async def test_press_hold_release(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "up", "a")
    assert sorted(take(keyboard)) == [("down", "space"), ("down", "up")]
    await press(ws, "up", "a")  # same state again: nothing new
    assert take(keyboard) == []
    await press(ws)
    assert sorted(take(keyboard)) == [("up", "space"), ("up", "up")]
    await ws.close()


async def test_diagonal_back_to_cardinal_releases_one_key(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "up", "right")
    take(keyboard)
    await press(ws, "up")
    assert take(keyboard) == [("up", "right")]
    await ws.close()


async def test_unknown_controls_are_ignored(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "up", "cmd", "q; rm -rf /")
    assert take(keyboard) == [("down", "up")]
    await ws.send_str("not json")
    await ws.send_json({"type": "state", "pressed": "up"})
    await asyncio.sleep(0.05)
    assert take(keyboard) == []
    await ws.close()


async def test_layout_switch_while_holding(client, keyboard, state_path):
    ws, _ = await connect(client)
    await press(ws, "up")
    take(keyboard)
    await ws.send_json({"type": "layout", "name": "wasd"})
    config = await ws.receive_json()
    assert config["layout"] == "wasd"
    assert config["keys"]["b"] == "shift"
    assert take(keyboard) == [("up", "up"), ("down", "w")]
    assert json.loads(state_path.read_text())["layout"] == "wasd"
    await ws.close()


async def test_modifier_goes_down_first_and_up_last(client, keyboard):
    ws, _ = await connect(client)
    await ws.send_json({"type": "layout", "name": "wasd"})
    await ws.receive_json()
    await press(ws, "a", "b")
    assert take(keyboard) == [("down", "shift"), ("down", "space")]
    await press(ws)
    assert take(keyboard) == [("up", "space"), ("up", "shift")]
    await ws.close()


async def test_disconnect_releases_everything(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "a", "left")
    take(keyboard)
    await ws.close()
    await asyncio.sleep(0.1)
    assert sorted(take(keyboard)) == [("up", "left"), ("up", "space")]


async def test_silent_phone_gets_released_and_dropped(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "a")
    take(keyboard)
    await asyncio.sleep(1.0)  # timeout is 0.6 s in these tests
    assert take(keyboard) == [("up", "space")]
    msg = await ws.receive(timeout=1)
    assert ws.closed or msg.type.name in ("CLOSE", "CLOSED", "CLOSING")


async def test_pings_keep_a_held_key_down(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "a")
    take(keyboard)
    for _ in range(6):
        await ws.send_json({"type": "ping"})
        assert (await ws.receive_json())["type"] == "pong"
        await asyncio.sleep(0.2)
    assert take(keyboard) == []
    await ws.close()


async def test_two_phones_share_a_key(client, keyboard):
    ws1, _ = await connect(client)
    ws2, _ = await connect(client)
    await press(ws1, "a")
    await press(ws2, "a")
    assert take(keyboard) == [("down", "space")]
    await press(ws1)
    assert take(keyboard) == []
    await press(ws2)
    assert take(keyboard) == [("up", "space")]
    await ws1.close()
    await ws2.close()


async def test_playstation_layout_config_and_shoulders(client, keyboard):
    ws, _ = await connect(client)
    await ws.send_json({"type": "layout", "name": "playstation"})
    config = await ws.receive_json()
    assert config["style"] == "playstation"
    assert config["stickSprint"] == "r1"
    assert config["names"]["x"] == "□"
    assert config["keys"]["l1"] == "q" and config["keys"]["select"] == "backspace"
    await press(ws, "x", "r1")
    assert sorted(take(keyboard)) == [("down", "a"), ("down", "e")]
    await press(ws)
    take(keyboard)
    await ws.close()


async def test_control_missing_from_layout_presses_nothing(client, keyboard):
    ws, _ = await connect(client)
    await press(ws, "l1", "up")  # arrows has no L1
    assert take(keyboard) == [("down", "up")]
    await ws.close()


async def test_quick_tap_stays_down_for_the_minimum_hold(held_client, keyboard):
    ws, _ = await connect(held_client)
    # Press and release arrive together, as when Wi-Fi bunches them.
    await ws.send_json({"type": "state", "pressed": ["a"]})
    await ws.send_json({"type": "state", "pressed": []})
    await asyncio.sleep(0.02)
    assert take(keyboard) == [("down", "space")]
    await asyncio.sleep(server.MIN_HOLD)
    assert take(keyboard) == [("up", "space")]
    await ws.close()


async def test_repress_during_the_minimum_hold_keeps_the_key_down(held_client, keyboard):
    ws, _ = await connect(held_client)
    for pressed in (["a"], [], ["a"]):
        await ws.send_json({"type": "state", "pressed": pressed})
    await asyncio.sleep(server.MIN_HOLD * 2)
    assert take(keyboard) == [("down", "space")]  # one press, never released in between
    await press(ws)
    await asyncio.sleep(server.MIN_HOLD)
    assert take(keyboard) == [("up", "space")]
    await ws.close()


async def test_long_press_is_not_delayed(held_client, keyboard):
    ws, _ = await connect(held_client)
    await press(ws, "a")
    await asyncio.sleep(server.MIN_HOLD)
    take(keyboard)
    await ws.send_json({"type": "state", "pressed": []})
    await asyncio.sleep(0.01)
    assert take(keyboard) == [("up", "space")]
    await ws.close()


async def test_shift_still_comes_up_last_when_a_release_is_delayed(held_client, keyboard):
    ws, _ = await connect(held_client)
    await ws.send_json({"type": "layout", "name": "wasd"})
    await ws.receive_json()
    await press(ws, "b")              # shift, held for a while
    await asyncio.sleep(server.MIN_HOLD)
    await ws.send_json({"type": "state", "pressed": ["a", "b"]})
    await ws.send_json({"type": "state", "pressed": []})  # quick tap on space, then let go of both
    await asyncio.sleep(server.MIN_HOLD * 2)
    assert take(keyboard) == [("down", "shift"), ("down", "space"), ("up", "space"), ("up", "shift")]
    await ws.close()


def test_release_all_lets_go_at_once():
    keyboard = DryRunKeyboard()
    hub = server.Hub(keyboard, LAYOUTS, "arrows")

    async def scenario():
        hub.phones.append(server.Phone(ws=None, pressed={"a", "up"}))
        hub.sync()
        hub.phones[0].pressed = set()
        hub.sync()                    # releases are now waiting for MIN_HOLD
        hub.release_all()
        assert sorted(keyboard.events) == [("down", "space"), ("down", "up"), ("up", "space"), ("up", "up")]
        assert not hub.pending and not hub.held

    asyncio.run(scenario())

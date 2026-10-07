"""The setup API: who may use it, what it accepts, and what it changes on phones and disk."""

import asyncio
import copy
import json
from pathlib import Path
from unittest import mock

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import server
from keyboard import DryRunKeyboard

ROOT = Path(__file__).resolve().parent.parent
LAYOUTS, DEFAULT = server.load_layouts(ROOT / "layouts.json")
TOKEN = "setup-token"
HEADERS = {"X-Phone-Joystick": "setup"}


@pytest.fixture
def keyboard():
    return DryRunKeyboard()


@pytest.fixture
def paths(tmp_path):
    return tmp_path / "state.json", tmp_path / "profiles.json"


@pytest.fixture
async def client(aiohttp_client, keyboard, paths):
    state, profiles = paths
    app = server.create_app(keyboard, copy.deepcopy(LAYOUTS), "arrows", TOKEN, state_path=state,
                            profiles_path=profiles, min_hold=0)
    return await aiohttp_client(app)


def edited(change):
    layouts = copy.deepcopy(LAYOUTS)
    change(layouts)
    return layouts


def request_from(remote, host="127.0.0.1:8777", headers=HEADERS):
    transport = mock.Mock()
    transport.get_extra_info.side_effect = lambda name, default=None: (remote, 50000) if name == "peername" else default
    return make_mocked_request("GET", "/api/profiles", headers={"Host": host, **headers}, transport=transport)


def test_only_this_computer_may_change_the_keys():
    server.local_only(request_from("127.0.0.1"))
    server.local_only(request_from("::1", host="[::1]:8777"))
    server.local_only(request_from("127.0.0.1", host="localhost:8777"))
    for request in (request_from("10.12.13.48"),                      # a phone on the Wi-Fi
                    request_from("127.0.0.1", host="evil.example"),    # DNS rebinding
                    request_from("127.0.0.1", headers={})):            # a cross-site form or fetch
        with pytest.raises(web.HTTPForbidden):
            server.local_only(request)


async def test_setup_page_and_api_need_the_header(client):
    assert (await client.get("/setup")).status == 200
    assert (await client.get("/api/profiles")).status == 403
    resp = await client.get("/api/profiles", headers=HEADERS)
    data = await resp.json()
    assert data["active"] == "arrows"
    assert set(data["layouts"]) == {"arrows", "wasd", "playstation"}
    assert "space" in data["keys"] and "l1" in data["controls"]


async def test_saving_updates_phones_disk_and_state(client, keyboard, paths):
    ws = await client.ws_connect(f"/ws?k={TOKEN}")
    await ws.receive_json()
    await ws.send_json({"type": "state", "pressed": ["a"]})          # holding A (space)
    await asyncio.sleep(0.05)

    def change(layouts):
        layouts["arrows"]["label"] = "Racing"
        layouts["arrows"]["keys"]["a"] = "k"
    resp = await client.put("/api/profiles", headers=HEADERS, json={"layouts": edited(change), "active": "arrows"})
    assert resp.status == 200
    config = await ws.receive_json()
    assert config["keys"]["a"] == "k"
    assert [l["label"] for l in config["layouts"]][0] == "Racing"
    await asyncio.sleep(0.05)
    assert keyboard.events[-2:] == [("up", "space"), ("down", "k")]  # the held button follows the new key

    state, profiles = paths
    saved, active = server.load_profiles(profiles)
    assert saved["arrows"]["keys"]["a"] == "k" and active == "arrows"
    assert json.loads(state.read_text(encoding="utf-8"))["layout"] == "arrows"
    await ws.close()


async def test_deleting_the_active_profile_switches_the_phones(client):
    ws = await client.ws_connect(f"/ws?k={TOKEN}")
    await ws.receive_json()
    layouts = edited(lambda l: l.pop("arrows"))
    resp = await client.put("/api/profiles", headers=HEADERS, json={"layouts": layouts, "active": "wasd"})
    assert resp.status == 200
    config = await ws.receive_json()
    assert config["layout"] == "wasd"
    assert [l["id"] for l in config["layouts"]] == ["wasd", "playstation"]
    await ws.close()


@pytest.mark.parametrize("change, active", [
    (lambda l: l["arrows"]["keys"].update(a="ctrl"), "arrows"),
    (lambda l: l["arrows"].update(label="  "), "arrows"),
    (lambda l: l["arrows"].update(label="x" * 41), "arrows"),
    (lambda l: l["arrows"].update(stickSprint="r1"), "arrows"),      # R1 has no key in Arrows
    (lambda l: l["arrows"]["keys"].update(turbo="space"), "arrows"),
    (lambda l: l.update({"Bad Id!": copy.deepcopy(l["wasd"])}), "arrows"),
    (lambda l: None, "missing"),
    (lambda l: l.clear(), "arrows"),
])
async def test_bad_profiles_are_rejected_and_nothing_is_saved(client, paths, change, active):
    resp = await client.put("/api/profiles", headers=HEADERS, json={"layouts": edited(change), "active": active})
    assert resp.status == 400
    assert not paths[1].exists()


async def test_reset_brings_back_the_built_in_profiles(client, paths):
    await client.put("/api/profiles", headers=HEADERS,
                     json={"layouts": edited(lambda l: l.pop("playstation")), "active": "wasd"})
    resp = await client.post("/api/profiles/reset", headers=HEADERS)
    data = await resp.json()
    assert set(data["layouts"]) == {"arrows", "wasd", "playstation"}
    assert data["active"] == "wasd"
    assert server.load_profiles(paths[1])[0] == LAYOUTS


def test_a_broken_profiles_file_falls_back_to_the_built_in_ones(tmp_path):
    broken = tmp_path / "profiles.json"
    broken.write_text('{"layouts": {"x": {"label": "X", "keys": {"a": "ctrl"}}}}', encoding="utf-8")
    assert server.load_profiles(broken)[0] == LAYOUTS
    assert server.load_profiles(tmp_path / "missing.json")[0] == LAYOUTS


async def test_language_is_saved_and_sent_to_phones(client, paths):
    ws = await client.ws_connect(f"/ws?k={TOKEN}")
    assert (await ws.receive_json())["lang"] == ""
    resp = await client.post("/api/lang", headers=HEADERS, json={"lang": "pt"})
    assert resp.status == 200 and (await resp.json())["lang"] == "pt"
    assert (await ws.receive_json())["lang"] == "pt"
    assert server.load_state(paths[0])["lang"] == "pt"
    assert (await client.post("/api/lang", headers=HEADERS, json={"lang": "fr"})).status == 400
    assert (await client.post("/api/lang", json={"lang": "es"})).status == 403
    await ws.close()

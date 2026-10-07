"""The real controller page in a touch-emulated phone browser, driven with multi-touch.

Key presses are recorded by DryRunKeyboard, nothing reaches the Mac.
"""

import asyncio
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

import server
from keyboard import DryRunKeyboard

ROOT = Path(__file__).resolve().parent.parent
LAYOUTS, _ = server.load_layouts(ROOT / "layouts.json")
TOKEN = "ui-token"
SHOTS = ROOT / "tests" / "screenshots"

VIEWPORTS = {
    "iphone-15-landscape": (852, 393),
    "iphone-se-landscape": (667, 375),
    "iphone-15-portrait": (393, 852),
    "iphone-15-safari-landscape": (750, 340),  # Safari bars eat width and height
    "pixel-7-landscape": (915, 412),
    "pixel-7-portrait": (412, 915),
}


@pytest.fixture
def keyboard():
    return DryRunKeyboard()


@pytest.fixture
def app(keyboard, tmp_path):
    return server.create_app(keyboard, LAYOUTS, "arrows", TOKEN, state_path=tmp_path / "state.json")


@pytest.fixture
async def base_url(aiohttp_server, app):
    srv = await aiohttp_server(app)
    return f"http://127.0.0.1:{srv.port}/?k={TOKEN}"


@pytest.fixture
async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        yield b
        await b.close()


async def open_phone(browser, url, size, locale="es-AR"):
    ctx = await browser.new_context(
        viewport={"width": size[0], "height": size[1]}, device_scale_factor=3,
        is_mobile=True, has_touch=True, locale=locale,
    )
    page = await ctx.new_page()
    await page.goto(url)
    await page.wait_for_function("document.getElementById('status').dataset.state === 'on'")
    cdp = await ctx.new_cdp_session(page)
    return page, cdp


async def touch(cdp, kind, points):
    """points: {id: (x, y)} for every finger still on the screen.

    For touchEnd, list only the fingers being lifted; an empty touchEnd lifts all of them.
    """
    await cdp.send("Input.dispatchTouchEvent", {
        "type": kind,
        "touchPoints": [{"x": x, "y": y, "id": i, "radiusX": 8, "radiusY": 8} for i, (x, y) in points.items()],
    })


async def center(page, selector):
    box = await page.locator(selector).bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


async def held(keyboard):
    await asyncio.sleep(0.15)
    keys = set()
    for kind, key in keyboard.events:
        (keys.add if kind == "down" else keys.discard)(key)
    return keys


async def test_stick_buttons_multitouch_and_layouts(browser, base_url, keyboard):
    page, cdp = await open_phone(browser, base_url, VIEWPORTS["iphone-15-landscape"])
    sx, sy = await center(page, "#stick-zone")

    # Stick: up, diagonal, right, back to center.
    await touch(cdp, "touchStart", {1: (sx, sy)})
    await touch(cdp, "touchMove", {1: (sx, sy - 55)})
    assert await held(keyboard) == {"up"}
    await touch(cdp, "touchMove", {1: (sx + 40, sy - 40)})
    assert await held(keyboard) == {"up", "right"}
    await touch(cdp, "touchMove", {1: (sx + 55, sy - 5)})
    assert await held(keyboard) == {"right"}
    await touch(cdp, "touchMove", {1: (sx + 5, sy)})  # inside the dead zone
    assert await held(keyboard) == set()
    await touch(cdp, "touchMove", {1: (sx - 50, sy + 10)})
    assert await held(keyboard) == {"left"}

    # Second finger presses A while the stick is held, then slides to B.
    ax, ay = await center(page, ".btn.a")
    bx, by = await center(page, ".btn.b")
    await touch(cdp, "touchStart", {1: (sx - 50, sy + 10), 2: (ax, ay)})
    assert await held(keyboard) == {"left", "space"}
    assert await page.locator(".btn.a.pressed").count() == 1
    await touch(cdp, "touchMove", {1: (sx - 50, sy + 10), 2: (bx, by)})
    assert await held(keyboard) == {"left", "z"}
    await touch(cdp, "touchEnd", {2: (bx, by)})  # lift finger 2 only
    assert await held(keyboard) == {"left"}
    await touch(cdp, "touchEnd", {})
    assert await held(keyboard) == set()

    # Start and Select.
    tx, ty = await center(page, '[data-control="start"]')
    await touch(cdp, "touchStart", {3: (tx, ty)})
    assert await held(keyboard) == {"enter"}
    await touch(cdp, "touchEnd", {})
    assert await held(keyboard) == set()

    # Switch to WASD from the phone.
    await page.get_by_role("radio", name="WASD").tap()
    await page.wait_for_function("document.querySelector('[data-control=b] .key').textContent === 'Shift'")
    assert await page.get_by_role("radio", name="WASD").get_attribute("aria-checked") == "true"
    await touch(cdp, "touchStart", {1: (sx, sy)})
    await touch(cdp, "touchMove", {1: (sx, sy - 55)})
    assert await held(keyboard) == {"w"}
    await touch(cdp, "touchEnd", {})
    assert await held(keyboard) == set()


async def test_leaving_the_page_releases_keys(browser, base_url, keyboard):
    page, cdp = await open_phone(browser, base_url, VIEWPORTS["iphone-15-landscape"])
    ax, ay = await center(page, ".btn.a")
    await touch(cdp, "touchStart", {1: (ax, ay)})
    assert await held(keyboard) == {"space"}
    await page.evaluate("window.dispatchEvent(new Event('blur'))")
    assert await held(keyboard) == set()


async def choose_layout(page, label):
    await page.get_by_role("radio", name=label).tap()
    await page.wait_for_function(
        f"[...document.querySelectorAll('#layouts button')].some(b => b.textContent === {label!r} "
        "&& b.getAttribute('aria-checked') === 'true')")


async def test_playstation_layout(browser, base_url, keyboard):
    page, cdp = await open_phone(browser, base_url, VIEWPORTS["iphone-15-landscape"])
    assert not await page.locator(".shoulder.l1").is_visible()  # arrows has no L1/R1
    await choose_layout(page, "PlayStation")
    assert await page.evaluate("document.body.dataset.style") == "playstation"
    names = {c: await page.locator(f".btn.{c} .name").text_content() for c in "abxy"}
    assert names == {"a": "✕", "b": "○", "x": "□", "y": "△"}
    assert await page.locator(".shoulder.l1").is_visible() and await page.locator(".shoulder.r1").is_visible()

    for selector, key in [(".btn.x", "a"), (".btn.b", "d"), (".btn.a", "x"), (".btn.y", "w"),
                          (".shoulder.l1", "q"), (".shoulder.r1", "e"),
                          ('[data-control="select"]', "backspace"), ('[data-control="start"]', "space")]:
        x, y = await center(page, selector)
        await touch(cdp, "touchStart", {1: (x, y)})
        assert await held(keyboard) == {key}, selector
        await touch(cdp, "touchEnd", {})
        assert await held(keyboard) == set()

    # Sprint while running and passing: stick + R1 + ✕ at once.
    sx, sy = await center(page, "#stick-zone")
    rx, ry = await center(page, ".shoulder.r1")
    ax, ay = await center(page, ".btn.a")
    await touch(cdp, "touchStart", {1: (sx, sy)})
    await touch(cdp, "touchMove", {1: (sx + 55, sy)})
    await touch(cdp, "touchStart", {1: (sx + 55, sy), 2: (rx, ry)})
    await touch(cdp, "touchStart", {1: (sx + 55, sy), 2: (rx, ry), 3: (ax, ay)})
    assert await held(keyboard) == {"right", "e", "x"}
    await touch(cdp, "touchEnd", {})
    assert await held(keyboard) == set()

    # Football mode: the stick at the edge of its ring also holds R1 (E); arrows never sprints.
    await touch(cdp, "touchStart", {1: (sx, sy)})
    await touch(cdp, "touchMove", {1: (sx + 48, sy)})       # 0.8 of the radius: run
    assert await held(keyboard) == {"right"}
    await touch(cdp, "touchMove", {1: (sx + 90, sy)})       # past the edge: sprint
    assert await held(keyboard) == {"right", "e"}
    assert await page.locator("#stick-zone.sprint").count() == 1
    assert await page.locator(".shoulder.r1.auto").count() == 1
    assert await page.locator(".shoulder.r1").evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(90, 200, 250)"
    await touch(cdp, "touchMove", {1: (sx + 54, sy - 4)})   # 0.9: still sprinting (hysteresis)
    assert await held(keyboard) == {"right", "e"}
    await touch(cdp, "touchMove", {1: (sx + 45, sy)})       # 0.75: back to running
    assert await held(keyboard) == {"right"}
    assert await page.locator("#stick-zone.sprint").count() == 0
    assert await page.locator(".shoulder.r1.auto").count() == 0
    await touch(cdp, "touchMove", {1: (sx, sy - 95)})       # sprint upwards
    assert await held(keyboard) == {"up", "e"}
    await touch(cdp, "touchEnd", {})
    assert await held(keyboard) == set()

    # Back to arrows: the shoulders disappear and nothing stays pressed.
    await choose_layout(page, "Flechas")
    assert not await page.locator(".shoulder.r1").is_visible()
    assert await page.locator(".btn.x .name").text_content() == "X"
    await touch(cdp, "touchStart", {1: (sx, sy)})
    await touch(cdp, "touchMove", {1: (sx + 95, sy)})
    assert await held(keyboard) == {"right"}
    await touch(cdp, "touchEnd", {})


async def test_touches_never_zoom_or_scroll(browser, base_url):
    page, cdp = await open_phone(browser, base_url, VIEWPORTS["iphone-15-landscape"])
    await page.evaluate("""() => {
        window.prevented = [];
        window.addEventListener('touchstart', e => window.prevented.push(e.defaultPrevented));
    }""")
    w, h = VIEWPORTS["iphone-15-landscape"]
    for x, y in [(w / 2, h / 2), (w / 2, 20), (10, h - 10), (w - 10, h - 10), (w / 2, h - 5)]:
        await touch(cdp, "touchStart", {1: (x, y)})
        await touch(cdp, "touchEnd", {})
    assert await page.evaluate("window.prevented") == [True] * 5


async def test_reloads_when_the_server_changes(browser, base_url, app, monkeypatch):
    page, _ = await open_phone(browser, base_url, VIEWPORTS["iphone-15-landscape"])
    await page.evaluate("window.marker = 1")
    monkeypatch.setattr(server, "BUILD", "next-build")  # as if the server restarted with new code
    async with page.expect_event("load", timeout=10_000):
        for phone in list(app[server.HUB].phones):
            await phone.ws.close()
    assert await page.evaluate("window.marker") is None


@pytest.mark.parametrize("layout", ["Flechas", "PlayStation"])
@pytest.mark.parametrize("name", list(VIEWPORTS))
async def test_layout_fits(browser, base_url, name, layout):
    page, _ = await open_phone(browser, base_url, VIEWPORTS[name])
    await choose_layout(page, layout)
    SHOTS.mkdir(exist_ok=True)
    await page.screenshot(path=SHOTS / f"{name}-{layout.lower()}.png")
    width, height = VIEWPORTS[name]
    selectors = [".status", "#layouts", ".btn.a", ".btn.b", ".btn.x", ".btn.y",
                 '[data-control="select"]', '[data-control="start"]', ".shoulder.l1", ".shoulder.r1"]
    boxes = {}
    for sel in selectors:
        if not await page.locator(sel).is_visible():
            continue
        box = await page.locator(sel).bounding_box()
        assert box["x"] >= 0 and box["y"] >= 0, (name, sel, box)
        assert box["x"] + box["width"] <= width + 0.5 and box["y"] + box["height"] <= height + 0.5, (name, sel, box)
        boxes[sel] = box
    assert (".shoulder.l1" in boxes) == (layout == "PlayStation")
    # No two controls overlap.
    names = list(boxes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            A, B = boxes[a], boxes[b]
            overlap = (A["x"] < B["x"] + B["width"] and B["x"] < A["x"] + A["width"]
                       and A["y"] < B["y"] + B["height"] and B["y"] < A["y"] + A["height"])
            assert not overlap, (name, layout, a, b)
    # Touch targets of at least 44 pt wide (Apple HIG).
    for sel in names[2:]:
        assert boxes[sel]["width"] >= 44 and boxes[sel]["height"] >= 40, (name, sel, boxes[sel])
    # Labels are not clipped.
    clipped = await page.evaluate("""() => [...document.querySelectorAll('.key, .name, .layouts button')]
        .filter(el => el.offsetParent && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent)""")
    assert clipped == [], (name, clipped)


async def test_english_phone_gets_english_labels(browser, base_url):
    page, _ = await open_phone(browser, base_url, VIEWPORTS["pixel-7-landscape"], locale="en-US")
    assert await page.locator("#status-text").text_content() == "Connected"
    assert await page.locator('[data-control="a"] .key').text_content() == "Space"
    await choose_layout(page, "PlayStation")
    assert await page.locator('[data-control="select"] .key').text_content() == "Backspace"
    assert await page.get_by_role("radio", name="Arrows").count() == 1


async def test_language_chosen_on_the_computer_reaches_the_phone(browser, base_url, app):
    page, _ = await open_phone(browser, base_url, VIEWPORTS["iphone-15-landscape"], locale="es-AR")
    assert await page.locator("#status-text").text_content() == "Conectado"
    app[server.HUB].lang = "pt"
    await server.broadcast(app)
    await page.wait_for_function("document.querySelector('[data-control=select] .key') && document.documentElement.lang === 'pt'")
    await page.wait_for_function("document.getElementById('status-text').textContent === 'Conectado'")
    assert await page.get_by_role("radio", name="Setas").count() == 1
    await choose_layout(page, "PlayStation")
    assert await page.locator('[data-control="select"] .key').text_content() == "Apagar"
    assert await page.locator('[data-control="start"] .key').text_content() == "Espaço"

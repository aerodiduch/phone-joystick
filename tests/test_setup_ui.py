"""The setup page in a real browser, with a phone page open at the same time."""

import asyncio
import copy
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

import server
from keyboard import DryRunKeyboard

ROOT = Path(__file__).resolve().parent.parent
LAYOUTS, _ = server.load_layouts(ROOT / "layouts.json")
TOKEN = "setup-ui"
SHOTS = ROOT / "tests" / "screenshots"


@pytest.fixture
def keyboard():
    return DryRunKeyboard()


@pytest.fixture
def app(keyboard, tmp_path):
    return server.create_app(keyboard, copy.deepcopy(LAYOUTS), "playstation", TOKEN,
                             state_path=tmp_path / "state.json", profiles_path=tmp_path / "profiles.json")


@pytest.fixture
async def base(aiohttp_server, app):
    srv = await aiohttp_server(app, host="127.0.0.1")
    return f"http://127.0.0.1:{srv.port}"


@pytest.fixture
async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        yield b
        await b.close()


async def open_setup(browser, base, width=1280, height=900):
    ctx = await browser.new_context(viewport={"width": width, "height": height}, locale="es-AR")
    page = await ctx.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(error))
    await page.goto(f"{base}/setup")
    await page.wait_for_selector(".profile")
    page.errors = errors
    return page


async def open_phone(browser, base, size=(852, 393)):
    ctx = await browser.new_context(viewport={"width": size[0], "height": size[1]}, is_mobile=True,
                                    has_touch=True, locale="es-AR")
    page = await ctx.new_page()
    await page.goto(f"{base}/?k={TOKEN}")
    await page.wait_for_function("document.getElementById('status').dataset.state === 'on'")
    return page


async def saved(page):
    await page.wait_for_function("document.getElementById('save-status').textContent === 'Guardado'")


async def until(check, timeout=3.0):
    """Waits for the server side to reach a state; the status text can lag one save behind."""
    for _ in range(int(timeout / 0.05)):
        if check():
            return
        await asyncio.sleep(0.05)
    assert check()


def profiles(app):
    return app[server.HUB].layouts


async def test_assign_a_key_and_the_phone_follows(browser, base, app):
    setup, phone = await open_setup(browser, base), await open_phone(browser, base)
    assert await phone.locator('[data-control="a"] .key').text_content() == "X"

    await setup.click('.chip[data-control="a"]')
    assert await setup.locator("#capture-text").text_content() == "Apretá la tecla para ✕"
    await setup.keyboard.press("k")
    await saved(setup)
    assert profiles(app)["playstation"]["keys"]["a"] == "k"
    await phone.wait_for_function("document.querySelector('[data-control=a] .key').textContent === 'K'")

    # Ctrl combos are refused and the capture stays open.
    await setup.click('.chip[data-control="b"]')
    await setup.keyboard.press("Control+k")
    assert "no se puede usar" in await setup.locator("#capture-text").text_content()
    await setup.keyboard.press("Tab")             # Tab is a valid key: it must not move the focus
    await saved(setup)
    assert profiles(app)["playstation"]["keys"]["b"] == "tab"

    # A control without a key disappears from the phone.
    await setup.click('.chip[data-control="l1"]')
    await setup.click("#clear-key")
    await saved(setup)
    assert "l1" not in profiles(app)["playstation"]["keys"]
    await phone.wait_for_function("document.querySelector('[data-control=l1]').hidden")
    assert setup.errors == []


async def test_profiles_new_rename_use_duplicate_delete(browser, base, app):
    setup, phone = await open_setup(browser, base), await open_phone(browser, base)

    await setup.click("#new-profile")
    await setup.fill("#profile-name", "Autos")
    await saved(setup)
    names = [p["label"] for p in profiles(app).values()]
    assert names == ["Arrows", "WASD", "PlayStation", "Autos"]
    assert await setup.locator(".profile[aria-current] .profile-name").text_content() == "Autos"

    await setup.click("#use-profile")
    await saved(setup)
    await phone.wait_for_function(
        "[...document.querySelectorAll('#layouts button')].some(b => b.textContent === 'Autos' && b.getAttribute('aria-checked') === 'true')")
    assert await setup.locator("#in-use").is_visible()

    await setup.click("#duplicate")
    await until(lambda: [p["label"] for p in profiles(app).values()][-1] == "Autos (copia)")

    # Cancelling the dialog keeps the profile; confirming deletes it.
    await setup.click("#delete")
    await setup.click("#confirm button[value=cancel]")
    assert len(profiles(app)) == 5
    await setup.click("#delete")
    await setup.click("#confirm-ok")
    await until(lambda: [p["label"] for p in profiles(app).values()] == ["Arrows", "WASD", "PlayStation", "Autos"])

    # Deleting the profile the phone uses moves the phone to the first one.
    await setup.click(".profile:has-text('Autos')")
    await setup.click("#delete")
    await setup.click("#confirm-ok")
    await until(lambda: app[server.HUB].layout == "arrows")
    await phone.wait_for_function(
        "[...document.querySelectorAll('#layouts button')].some(b => b.textContent === 'Flechas' && b.getAttribute('aria-checked') === 'true')")


async def test_style_stick_preset_and_sprint(browser, base, app):
    setup, phone = await open_setup(browser, base), await open_phone(browser, base)
    await setup.click(".profile:has-text('Flechas')")

    await setup.click("[data-style=playstation]")
    await saved(setup)
    assert profiles(app)["arrows"]["names"] == {"a": "✕", "b": "○", "x": "□", "y": "△"}

    await setup.click("[data-stick=wasd]")
    await saved(setup)
    assert {c: profiles(app)["arrows"]["keys"][c] for c in ("up", "down", "left", "right")} == \
        {"up": "w", "down": "s", "left": "a", "right": "d"}

    # Football mode is a switch; the run button can only be one that has a key.
    assert not await setup.is_checked("#football")
    assert not await setup.locator("#run-row").is_visible()
    await setup.click("#football")
    await saved(setup)
    assert profiles(app)["arrows"]["stickSprint"] == "a"          # Arrows has no R1: first button with a key
    options = await setup.locator("#sprint option").all_text_contents()
    assert not any(o.startswith("R1") for o in options)
    await setup.select_option("#sprint", "x")
    await saved(setup)
    assert profiles(app)["arrows"]["stickSprint"] == "x"
    await setup.click("#football")
    await saved(setup)
    assert "stickSprint" not in profiles(app)["arrows"]
    await setup.click("#football")
    await saved(setup)

    await setup.click("#use-profile")
    await saved(setup)
    await phone.wait_for_function("document.querySelector('[data-control=x] .name').textContent === '□'")


async def test_flags_switch_the_language_everywhere(browser, base, app, tmp_path):
    setup, phone = await open_setup(browser, base), await open_phone(browser, base)
    assert await setup.locator("[data-lang=es]").get_attribute("aria-checked") == "true"

    await setup.click("[data-lang=pt]")
    await setup.wait_for_function("document.querySelector('.profiles h2').textContent === 'Perfis'")
    assert await setup.locator("#new-profile").text_content() == "Novo perfil"
    assert await setup.locator("label[for=football]").text_content() == "Modo futebol"
    assert await setup.locator("[data-lang=pt]").get_attribute("aria-checked") == "true"
    assert app[server.HUB].lang == "pt"
    assert server.load_state(app[server.STATE_PATH])["lang"] == "pt"
    await phone.wait_for_function("document.querySelector('[data-control=start] .key').textContent === 'Espaço'")

    await setup.click("[data-lang=en]")
    await setup.wait_for_function("document.querySelector('.profiles h2').textContent === 'Profiles'")
    await phone.wait_for_function("document.querySelector('[data-control=start] .key').textContent === 'Space'")


async def test_reset_and_phone_switch_show_up_on_the_setup_page(browser, base, app):
    setup, phone = await open_setup(browser, base), await open_phone(browser, base)
    await setup.click("#new-profile")
    await saved(setup)
    await setup.click("#reset")
    await setup.click("#confirm-ok")
    await setup.wait_for_function("document.querySelectorAll('.profile').length === 3")
    assert len(profiles(app)) == 3

    # Switching profile on the phone moves the "En uso" mark on the computer.
    await phone.get_by_role("radio", name="WASD").tap()
    await setup.wait_for_function(
        "[...document.querySelectorAll('.profile')].find(b => b.textContent.includes('WASD')).querySelector('.tag')")


async def test_many_profiles_fold_into_a_list_on_the_phone(browser, base, app, keyboard):
    setup = await open_setup(browser, base)
    for name in ("Fútbol con amigos", "Carreras de autos", "Plataformas retro"):
        await setup.click("#new-profile")
        await setup.fill("#profile-name", name)
    await saved(setup)

    phone = await open_phone(browser, base, size=(393, 852))
    assert await phone.locator("#layouts.compact").count() == 1
    SHOTS.mkdir(exist_ok=True)
    await phone.screenshot(path=SHOTS / "phone-compact.png")
    await phone.locator("#layouts button").tap()
    assert await phone.locator("#sheet").is_visible()
    await phone.screenshot(path=SHOTS / "phone-compact-open.png")
    keyboard.events.clear()
    await phone.get_by_role("radio", name="Carreras de autos").tap()
    await asyncio.sleep(0.2)
    assert app[server.HUB].layout != "playstation"
    assert profiles(app)[app[server.HUB].layout]["label"] == "Carreras de autos"
    assert not await phone.locator("#sheet").is_visible()
    assert keyboard.events == []                 # the tap on the list pressed no game button


@pytest.mark.parametrize("width", [1280, 390])
async def test_setup_page_fits(browser, base, width):
    setup = await open_setup(browser, base, width=width)
    SHOTS.mkdir(exist_ok=True)
    await setup.screenshot(path=SHOTS / f"setup-{width}.png", full_page=True)
    assert await setup.evaluate("document.documentElement.scrollWidth") <= width
    overflowing = await setup.evaluate("""() => [...document.querySelectorAll('.chip, .button, .segmented, .select, .name-input')]
        .filter(el => el.offsetParent).map(el => el.getBoundingClientRect())
        .filter(r => r.left < 0 || r.right > innerWidth + 0.5).length""")
    assert overflowing == 0
    clipped = await setup.evaluate("""() => [...document.querySelectorAll('.chip .key, .chip .name, .button, .option-label')]
        .filter(el => el.offsetParent && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent)""")
    assert clipped == []

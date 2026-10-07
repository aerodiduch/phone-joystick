# Phone Joystick

[![CI](https://github.com/aerodiduch/phone-joystick/actions/workflows/ci.yml/badge.svg)](https://github.com/aerodiduch/phone-joystick/actions/workflows/ci.yml) [![Release](https://img.shields.io/github/v/release/aerodiduch/phone-joystick)](https://github.com/aerodiduch/phone-joystick/releases/latest) [![Downloads](https://img.shields.io/github/downloads/aerodiduch/phone-joystick/total)](https://github.com/aerodiduch/phone-joystick/releases) [![License: MIT](https://img.shields.io/github/license/aerodiduch/phone-joystick)](LICENSE) ![Windows | macOS](https://img.shields.io/badge/computer-Windows%20%7C%20macOS-0078D4) ![iPhone | Android](https://img.shields.io/badge/phone-iPhone%20%7C%20Android-34A853) ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)

[Español](README.es.md) · [Português](README.pt.md)

![A phone used as a gamepad in front of a laptop running a football game](docs/cover.jpg)

Phone Joystick turns your phone into a joystick for your laptop. It's meant for when you're away from your setup: at the office, in a hotel room, on vacation. Scan a QR code with your phone and play. The phone shows a stick and buttons in its browser, and the computer turns each touch into a key press, so any game you play with the keyboard works. I built it to play [PES 6 Web](https://pes6.optijuegos.net/) in my laptop's browser at work, and the PlayStation profile uses the keys I set up in that game.

- iPhone (Safari) and Android (Chrome). Nothing to install on the phone; you scan a QR code.
- Windows and macOS.
- A D-pad or an analog stick, switched from the phone's top bar, plus four face buttons, L1, R1, Start and Select. You choose the key for each one on a [setup page](#setup-page), and keep as many profiles as you want.
- Several fingers at once, and a finger can slide from one button to the next.
- Football mode: sliding your thumb a little past the edge of the D-pad or the stick also holds the run button, so you sprint while your right thumb passes and shoots.
- In Spanish, Portuguese and English.
- If the phone locks or the Wi-Fi drops, every key is released within 1.5 seconds.

## Windows

1. Download [`phone-joystick.exe`](https://github.com/aerodiduch/phone-joystick/releases/latest/download/phone-joystick.exe) from the latest release.
2. Double-click it. The file isn't signed, so Windows may show *Windows protected your PC*. Click **More info**, then **Run anyway**.
3. When the firewall asks, allow access on **private networks**. Without it, the phone can't reach the computer.
4. A window opens with a QR code. Scan it with the phone's camera. Phone and computer have to be on the same Wi-Fi.
5. Open the game and click its window so it's in front. Keys go to whatever window is in front.
6. To choose your keys, open the [setup page](#setup-page).

### Check the download

Each release lists the SHA-256 of `phone-joystick.exe` next to the file, and also ships it in `phone-joystick.exe.sha256`. Compute yours and compare:

```powershell
Get-FileHash .\phone-joystick.exe -Algorithm SHA256
```

(`certutil -hashfile phone-joystick.exe SHA256` in `cmd` gives the same value.) If they don't match, don't run the file.

From v0.3.2 on, each `.exe` also carries a GitHub attestation that it was built by this repository's workflow from a given commit. With the [GitHub CLI](https://cli.github.com/):

```powershell
gh attestation verify .\phone-joystick.exe -R aerodiduch/phone-joystick
```

### Build the .exe yourself

If you'd rather not run a file someone else built, build it from the code. You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Git](https://git-scm.com/download/win), or the code from **Code → Download ZIP**.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
git clone https://github.com/aerodiduch/phone-joystick
cd phone-joystick
uv sync
uv run pyinstaller --onefile --name phone-joystick --add-data "static;static" --add-data "layouts.json;." server.py
```

The file ends up in `dist\phone-joystick.exe`. It won't necessarily match the release's SHA-256 byte for byte; what you get is an `.exe` made from code you can read. You can also skip the `.exe` and run `uv run server.py` from that folder.

## macOS

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`).

```sh
git clone https://github.com/aerodiduch/phone-joystick
cd phone-joystick
uv run server.py
```

The first time, macOS asks for the **Accessibility** permission for your terminal app (Terminal, iTerm…). It's what lets a program press keys. Turn it on and the server carries on by itself.

Scan the QR code in the terminal with your phone, open the game and click its window. To choose your keys, open the [setup page](#setup-page).

## Profiles

These three come built in, and you can change them or add your own on the setup page. Switch profiles from the phone's top bar; the computer remembers the last one.

| Control | Arrows | WASD | PlayStation |
| --- | --- | --- | --- |
| Directions | ↑ ↓ ← → | W A S D | ↑ ↓ ← → |
| A / ✕ | Space | Space | X |
| B / ○ | Z | Shift | D |
| X / □ | X | E | A |
| Y / △ | C | Q | W |
| L1 | | | Q |
| R1 | | | E |
| Start | Enter | Enter | Space |
| Select | Esc | Esc | Backspace |
| Football mode | off | off | on (R1) |

## Setup page

![The setup page](docs/setup-en.jpg)

Open **http://localhost:8777/setup** in a browser on the computer that runs Phone Joystick. The window with the QR code shows this link too. The page only opens on that computer; a phone or another device on the network gets an error.

- **Keys.** You see the controller with the key under each control. Click a control and press the key you want. **No key** hides that control on the phone.
- **Profiles.** Create, duplicate, rename and delete them, and pick the one the phone uses with **Use on the phone**.
- **Directions.** Set them to arrows or WASD in one click, or click each one and assign it like any other control. The D-pad and the stick use the same keys.
- **Buttons.** Show them as A B X Y or as ✕ ○ □ △.
- **Football mode.** On a phone it's hard to hold the run button while you move. With football mode on, sliding your thumb a little past the edge of the D-pad or the stick's circle presses the run button for you, and the button lights up on the phone while it's held. You choose which button runs.
- **Language.** The flags at the top switch between Spanish, Portuguese and English, on this page and on the phone.
- **Vibration.** The phone gives a short vibration when you tap a button (on iPhone it buzzes when you lift your finger; Safari doesn't allow it any sooner). Turn it off under **On the phone**.

Changes save themselves and reach the phone at once, even in the middle of a match, without restarting anything. If you're holding a button when you change its key, the old key is released and the new one pressed.

Letters, digits, arrows, Space, Enter, Esc, Tab, Backspace and Shift can be assigned. Ctrl, Alt and Cmd can't, so nobody can send shortcuts to your computer from a phone.

Your profiles are saved in `profiles.json`, next to `server.py`, or in `%APPDATA%\phone-joystick\` with the `.exe`. **Go back to the built-in profiles**, below the list, restores the original three.

## If something doesn't work

- **The phone doesn't connect.** Check that both are on the same Wi-Fi. Office, hotel and guest networks often keep devices from seeing each other. Turn on your phone's hotspot, connect the computer to it and restart Phone Joystick, which shows a new QR code. A VPN can also block the local network; look for a "local network" or "LAN" option in its settings.
- **The phone connects but the game doesn't react.** Click the game window. On Windows, a game running as administrator ignores keys from normal programs; run `phone-joystick.exe` as administrator too.
- **The antivirus flags the `.exe`.** Apps packed with PyInstaller get false positives now and then. You can run from source instead: install uv and follow the macOS steps.

## Security

- Only phones with the key inside the QR code can connect. It's stored in `state.json`; delete that file to get a new key and a new QR code.
- The phone sends button names, never keys. The computer decides which key each button presses, from the list above.
- The page travels over plain HTTP on your local network, so someone on the same network could read the key. At home that's fine; on a shared network, close Phone Joystick when you stop playing.

## How it works

`server.py` (Python, aiohttp) serves the page and a WebSocket. The phone sends the set of controls it's holding whenever it changes, plus a ping every half second. The server presses or releases only the difference, with Quartz `CGEventPost` on macOS and `SendInput` with scan codes on Windows. Each key stays down at least 60 ms, so a game that reads the keyboard once per frame doesn't miss a quick tap. The stick is [nipplejs](https://github.com/yoannmoinet/nipplejs).

## Development

```sh
uv sync
uv run playwright install chromium
uv run pytest
```

The tests run the server and the real page in an emulated phone with multi-touch, without pressing any key. `tests/check_real_keys.py` does press real keys in a browser window it opens; run it only on a computer nobody is using.

## License

MIT. nipplejs is MIT too (`static/vendor/nipplejs-LICENSE`).

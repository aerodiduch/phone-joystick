# Phone Joystick

[Español](README.es.md)

Phone Joystick turns your phone into a joystick for your laptop. It's meant for when you're away from your setup: at the office, in a hotel room, on vacation. Scan a QR code with your phone and play. The phone shows a stick and buttons in its browser, and the computer turns each touch into a key press, so any game you play with the keyboard works. I built it to play [PES 6 Web](https://pes6.optijuegos.net/) in my laptop's browser at work, and the PlayStation layout uses the keys I set up in that game.

- iPhone (Safari) and Android (Chrome). Nothing to install on the phone; you scan a QR code.
- Windows and macOS.
- Stick with 8 directions, four face buttons, Start and Select. The PlayStation layout adds L1 and R1 and the ✕ ○ □ △ symbols.
- Several fingers at once, and a finger can slide from one button to the next.
- In the PlayStation layout, pushing the stick past its ring also holds R1, so you can sprint while your right thumb passes and shoots.
- If the phone locks or the Wi-Fi drops, every key is released within 1.5 seconds.

## Windows

1. Download [`phone-joystick.exe`](https://github.com/aerodiduch/phone-joystick/releases/latest/download/phone-joystick.exe) from the latest release.
2. Double-click it. The file isn't signed, so Windows may show *Windows protected your PC*. Click **More info**, then **Run anyway**.
3. When the firewall asks, allow access on **private networks**. Without it, the phone can't reach the computer.
4. A window opens with a QR code. Scan it with the phone's camera. Phone and computer have to be on the same Wi-Fi.
5. Open the game and click its window so it's in front. Keys go to whatever window is in front.

## macOS

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`).

```sh
git clone https://github.com/aerodiduch/phone-joystick
cd phone-joystick
uv run server.py
```

The first time, macOS asks for the **Accessibility** permission for your terminal app (Terminal, iTerm…). It's what lets a program press keys. Turn it on and the server carries on by itself.

Scan the QR code in the terminal with your phone, open the game and click its window.

## Layouts

Switch layouts from the phone. The computer remembers the last one.

| Control | Arrows | WASD | PlayStation |
| --- | --- | --- | --- |
| Stick | ↑ ↓ ← → | W A S D | ↑ ↓ ← → |
| A / ✕ | Space | Space | X |
| B / ○ | Z | Shift | D |
| X / □ | X | E | A |
| Y / △ | C | Q | W |
| L1 | | | Q |
| R1 | | | E |
| Start | Enter | Enter | Space |
| Select | Esc | Esc | Backspace |

### Your own keys

Layouts live in `layouts.json`. Running from source, edit the one in the repo. With the `.exe`, copy it to `%APPDATA%\phone-joystick\layouts.json` and edit that copy. Restart after changing it.

```json
"racing": {
  "label": "Racing",
  "keys": { "up": "w", "down": "s", "left": "a", "right": "d", "a": "space", "start": "escape" }
}
```

Controls: `up`, `down`, `left`, `right`, `a`, `b`, `x`, `y`, `l1`, `r1`, `start`, `select`. Controls left out don't show on the phone.
Keys: letters, digits, arrows (`up`, `down`, `left`, `right`), `space`, `enter`, `escape`, `tab`, `backspace` and `shift`. Ctrl, Alt and Cmd aren't allowed, so nobody can send shortcuts to your computer from a phone.

`"names"` changes what the buttons show (the PlayStation layout uses it for ✕ ○ □ △), and `"stickSprint": "r1"` makes the stick hold R1 when pushed past its ring.

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

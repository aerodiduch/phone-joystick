# Phone Joystick

[English](README.md)

Phone Joystick convierte tu teléfono en un control para jugar en la computadora. El teléfono muestra un stick y botones en el navegador, y la computadora convierte cada toque en una tecla, así que anda con cualquier juego que se juegue con teclado. Lo hice para jugar un juego de fútbol en el navegador de mi laptop, con el teléfono como joystick.

- iPhone (Safari) y Android (Chrome). En el teléfono no se instala nada; se escanea un código QR.
- Windows y macOS.
- Stick de 8 direcciones, cuatro botones, Start y Select. El esquema PlayStation suma L1 y R1 y los símbolos ✕ ○ □ △.
- Varios dedos a la vez, y un dedo puede deslizarse de un botón al otro.
- En el esquema PlayStation, si llevás el stick más allá del aro también se aprieta R1, así corrés mientras el pulgar derecho pasa y patea.
- Si el teléfono se bloquea o se corta la Wi-Fi, todas las teclas se sueltan en menos de 1,5 segundos.

## Windows

1. Descargá [`phone-joystick.exe`](https://github.com/aerodiduch/phone-joystick/releases/latest/download/phone-joystick.exe) de la última versión.
2. Abrilo con doble clic. El archivo no está firmado, así que Windows puede mostrar *Windows protegió su PC*. Hacé clic en **Más información** y después en **Ejecutar de todas formas**.
3. Cuando el firewall pregunte, permití el acceso en **redes privadas**. Si no, el teléfono no llega a la computadora.
4. Se abre una ventana con un código QR. Escanealo con la cámara del teléfono. El teléfono y la computadora tienen que estar en la misma Wi-Fi.
5. Abrí el juego y hacé clic en su ventana para que quede al frente. Las teclas van a la ventana que esté al frente.

## macOS

Necesitás [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`).

```sh
git clone https://github.com/aerodiduch/phone-joystick
cd phone-joystick
uv run server.py
```

La primera vez, macOS pide el permiso de **Accesibilidad** para la app de terminal (Terminal, iTerm…). Es lo que deja que un programa apriete teclas. Activalo y el servidor sigue solo.

Escaneá el QR de la terminal con el teléfono, abrí el juego y hacé clic en su ventana.

## Esquemas de teclas

El esquema se cambia desde el teléfono y la computadora recuerda el último.

| Control | Flechas | WASD | PlayStation |
| --- | --- | --- | --- |
| Stick | ↑ ↓ ← → | W A S D | ↑ ↓ ← → |
| A / ✕ | Espacio | Espacio | X |
| B / ○ | Z | Shift | D |
| X / □ | X | E | A |
| Y / △ | C | Q | W |
| L1 | | | Q |
| R1 | | | E |
| Start | Enter | Enter | Espacio |
| Select | Esc | Esc | Borrar |

### Tus propias teclas

Los esquemas están en `layouts.json`. Si lo corrés desde el código, editá el del repo. Con el `.exe`, copialo a `%APPDATA%\phone-joystick\layouts.json` y editá esa copia. Después de cambiarlo, reinicialo.

```json
"carreras": {
  "label": "Carreras",
  "keys": { "up": "w", "down": "s", "left": "a", "right": "d", "a": "space", "start": "escape" }
}
```

Controles: `up`, `down`, `left`, `right`, `a`, `b`, `x`, `y`, `l1`, `r1`, `start`, `select`. Los que no pongas no aparecen en el teléfono.
Teclas: letras, números, flechas (`up`, `down`, `left`, `right`), `space`, `enter`, `escape`, `tab`, `backspace` y `shift`. Ctrl, Alt y Cmd no se permiten, así nadie puede mandarle atajos a tu computadora desde un teléfono.

`"names"` cambia lo que muestran los botones (el esquema PlayStation lo usa para ✕ ○ □ △), y `"stickSprint": "r1"` hace que el stick apriete R1 cuando pasás el aro.

## Si algo no anda

- **El teléfono no se conecta.** Fijate que los dos estén en la misma Wi-Fi. Las redes de oficinas, hoteles y de invitados muchas veces no dejan que los equipos se vean entre sí. Prendé el hotspot del teléfono, conectá la computadora a esa red y reiniciá Phone Joystick, que muestra un QR nuevo. Una VPN también puede bloquear la red local; buscá una opción de "red local" o "LAN" en sus ajustes.
- **El teléfono se conecta pero el juego no responde.** Hacé clic en la ventana del juego. En Windows, un juego que corre como administrador ignora las teclas de los programas comunes; corré `phone-joystick.exe` como administrador también.
- **El antivirus marca el `.exe`.** Los programas empaquetados con PyInstaller a veces dan falsos positivos. Podés correrlo desde el código: instalá uv y seguí los pasos de macOS.

## Seguridad

- Solo se conectan los teléfonos que tienen la clave del QR. Está guardada en `state.json`; si borrás ese archivo, se genera otra clave y otro QR.
- El teléfono manda nombres de botones, nunca teclas. La computadora decide qué tecla aprieta cada botón, de la lista de arriba.
- La página viaja por HTTP sin cifrar en tu red local, así que alguien en la misma red podría leer la clave. En tu casa no hay problema; en una red compartida, cerrá Phone Joystick cuando dejes de jugar.

## Cómo funciona

`server.py` (Python, aiohttp) sirve la página y un WebSocket. El teléfono manda los controles que tiene apretados cada vez que cambian, más un ping cada medio segundo. El servidor aprieta o suelta solo la diferencia, con Quartz `CGEventPost` en macOS y `SendInput` con scan codes en Windows. Cada tecla queda apretada al menos 60 ms, para que un juego que lee el teclado una vez por cuadro no se pierda un toque rápido. El stick es [nipplejs](https://github.com/yoannmoinet/nipplejs).

## Desarrollo

```sh
uv sync
uv run playwright install chromium
uv run pytest
```

Los tests levantan el servidor y la página real en un teléfono emulado con multitoque, sin apretar ninguna tecla. `tests/check_real_keys.py` sí aprieta teclas de verdad en una ventana de navegador que abre; correlo solo en una computadora que nadie esté usando.

## Licencia

MIT. nipplejs también es MIT (`static/vendor/nipplejs-LICENSE`).

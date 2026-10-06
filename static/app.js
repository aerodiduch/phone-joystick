(() => {
  "use strict";

  const STICK_SIZE = 120;
  const STICK_ON = 0.3, STICK_OFF = 0.2;     // deflection that engages / releases the stick
  const AXIS_ON = 0.42, AXIS_OFF = 0.34;     // per-axis threshold: 8 sectors of 45°
  const SPRINT_ON = 1.3, SPRINT_OFF = 1.15;  // finger distance / stick radius
  const BUTTON_HIT = 1.15;                   // round buttons react a bit outside their edge
  const PING_MS = 500, PONG_TIMEOUT_MS = 2000;

  const lang = navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
  const TEXT = {
    es: { on: "Conectado", off: "Sin conexión", layouts: "Teclas", arrows: "Flechas",
          space: "Espacio", backspace: "Borrar" },
    en: { on: "Connected", off: "Disconnected", layouts: "Keys", arrows: "Arrows",
          space: "Space", backspace: "Backspace" },
  }[lang];
  const KEY_LABELS = { space: TEXT.space, backspace: TEXT.backspace, enter: "Enter", escape: "Esc",
                       tab: "Tab", shift: "Shift", up: "↑", down: "↓", left: "←", right: "→" };
  const keyLabel = (key) => KEY_LABELS[key] || key.toUpperCase();

  const token = new URLSearchParams(location.search).get("k") || "";
  const zone = document.getElementById("stick-zone");
  const layoutsEl = document.getElementById("layouts");
  const statusEl = document.getElementById("status");
  const statusText = document.getElementById("status-text");
  const controls = [...document.querySelectorAll("[data-control]")];
  document.documentElement.lang = lang;
  layoutsEl.setAttribute("aria-label", TEXT.layouts);
  statusText.textContent = TEXT.off;

  let stick = new Set();      // directions, plus the sprint control while sprinting
  let buttons = new Set();
  const pointers = new Map(); // pointerId -> control under that finger, or null
  let ws = null, lastPong = 0, lastSent = "";
  let build = null, stickSprint = "";

  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${scheme}://${location.host}/ws?k=${encodeURIComponent(token)}`);
    ws.onopen = () => { lastPong = Date.now(); lastSent = ""; send(); };
    ws.onmessage = (e) => {
      lastPong = Date.now();
      const msg = JSON.parse(e.data);
      if (msg.type === "config") applyConfig(msg);
    };
    ws.onclose = () => { ws = null; setTimeout(connect, 1000); };
  }

  function isOpen() { return ws && ws.readyState === WebSocket.OPEN; }

  function send() {
    const payload = JSON.stringify({ type: "state", pressed: [...stick, ...buttons].sort() });
    if (payload === lastSent || !isOpen()) return;
    ws.send(payload);
    lastSent = payload;
  }

  setInterval(() => {
    if (isOpen()) ws.send('{"type":"ping"}');
    const on = isOpen() && Date.now() - lastPong < PONG_TIMEOUT_MS;
    statusEl.dataset.state = on ? "on" : "off";
    statusText.textContent = on ? TEXT.on : TEXT.off;
  }, PING_MS);

  function applyConfig(msg) {
    if (build && msg.build !== build) return location.reload(); // the server restarted with new code
    build = msg.build;
    document.body.dataset.style = msg.style;
    stickSprint = msg.stickSprint;
    layoutsEl.replaceChildren(...msg.layouts.map(({ id, label }) => {
      const b = document.createElement("button");
      b.textContent = TEXT[id] || label;
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(id === msg.layout));
      // pointerup, not click: touchstart is cancelled below, so iOS never fires click.
      b.addEventListener("pointerup", () => {
        if (isOpen()) ws.send(JSON.stringify({ type: "layout", name: id }));
      });
      return b;
    }));
    for (const el of controls) {
      const control = el.dataset.control;
      const name = el.querySelector(".name");
      name.dataset.default ??= name.textContent;
      name.textContent = msg.names[control] || name.dataset.default;
      el.querySelector(".key").textContent = control in msg.keys ? keyLabel(msg.keys[control]) : "";
      el.hidden = !(control in msg.keys);
    }
    for (const [id, control] of pointers) {
      if (control && !(control in msg.keys)) pointers.set(id, null);
    }
    updateButtons();
  }

  const manager = nipplejs.create({
    zone,
    mode: "dynamic",
    size: STICK_SIZE,
    fadeTime: 80,
    color: { front: "rgba(236, 238, 241, 0.9)", back: "rgba(236, 238, 241, 0.14)" },
  });

  function setStick(next) {
    if (next.size === stick.size && [...next].every((d) => stick.has(d))) return;
    stick = next;
    render();
    send();
  }

  manager.on("start", () => zone.classList.add("active"));
  manager.on("end", () => { zone.classList.remove("active", "sprint"); setStick(new Set()); });
  manager.on("move", (evt) => {
    const { x, y } = evt.data.vector; // -1..1, y points up
    const magnitude = Math.min(Math.hypot(x, y), 1);
    if (magnitude < (stick.size ? STICK_OFF : STICK_ON)) {
      zone.classList.remove("sprint");
      return setStick(new Set());
    }
    const ux = x / Math.hypot(x, y), uy = y / Math.hypot(x, y);
    const next = new Set();
    const axis = (dir, v) => { if (v > (stick.has(dir) ? AXIS_OFF : AXIS_ON)) next.add(dir); };
    axis("right", ux); axis("left", -ux); axis("up", uy); axis("down", -uy);
    // Past the ring, the layout's sprint control goes down too (Xbox touch guide: joystick actionThreshold).
    const reach = evt.data.raw.distance / (STICK_SIZE / 2);
    if (stickSprint && reach > (stick.has(stickSprint) ? SPRINT_OFF : SPRINT_ON)) next.add(stickSprint);
    zone.classList.toggle("sprint", next.has(stickSprint));
    setStick(next);
  });

  // Buttons are hit-tested by position, so a finger can slide from one to the next.
  function controlAt(x, y) {
    for (const el of controls) {
      if (el.hidden) continue;
      const r = el.getBoundingClientRect();
      if (el.classList.contains("btn")) {
        const cx = r.left + r.width / 2, cy = r.top + r.height / 2, rad = (r.width / 2) * BUTTON_HIT;
        if ((x - cx) ** 2 + (y - cy) ** 2 <= rad * rad) return el.dataset.control;
      } else if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) {
        return el.dataset.control;
      }
    }
    return null;
  }

  function render() {
    for (const el of controls) {
      el.classList.toggle("pressed", buttons.has(el.dataset.control));
      el.classList.toggle("auto", stick.has(el.dataset.control));
    }
  }

  function updateButtons() {
    buttons = new Set([...pointers.values()].filter(Boolean));
    render();
    send();
  }

  document.addEventListener("pointerdown", (e) => {
    if (zone.contains(e.target) || layoutsEl.contains(e.target)) return;
    pointers.set(e.pointerId, controlAt(e.clientX, e.clientY));
    updateButtons();
  });
  document.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    pointers.set(e.pointerId, controlAt(e.clientX, e.clientY));
    updateButtons();
  });
  for (const type of ["pointerup", "pointercancel"]) {
    document.addEventListener(type, (e) => { if (pointers.delete(e.pointerId)) updateButtons(); });
  }

  function releaseAll() {
    pointers.clear();
    stick = new Set();
    updateButtons();
  }
  document.addEventListener("visibilitychange", () => { if (document.hidden) releaseAll(); });
  window.addEventListener("pagehide", releaseAll);
  window.addEventListener("blur", releaseAll);

  // iOS ignores user-scalable=no; cancelling every touchstart is what stops double-tap zoom.
  document.addEventListener("touchstart", (e) => e.preventDefault(), { passive: false });
  document.addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });
  document.addEventListener("gesturestart", (e) => e.preventDefault());
  document.addEventListener("contextmenu", (e) => e.preventDefault());

  connect();
})();

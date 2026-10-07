(() => {
  "use strict";

  const STICK_SIZE = 120;
  const STICK_ON = 0.3, STICK_OFF = 0.2;     // deflection that engages / releases the stick
  const AXIS_ON = 0.42, AXIS_OFF = 0.34;     // per-axis threshold: 8 sectors of 45°
  const SPRINT_ON = 1.3, SPRINT_OFF = 1.15;  // football mode: finger distance / stick radius, past the ring
  const BUTTON_HIT = 1.15;                   // round buttons react a bit outside their edge
  const PING_MS = 500, PONG_TIMEOUT_MS = 2000;

  const { t, keyLabel, layoutLabel } = window.PJ;

  const token = new URLSearchParams(location.search).get("k") || "";
  const zone = document.getElementById("stick-zone");
  const dpadZone = document.getElementById("dpad-zone");
  const dpad = document.getElementById("dpad");
  const arms = [...dpad.querySelectorAll("[data-dir]")];
  const modeEl = document.getElementById("mode");
  const layoutsEl = document.getElementById("layouts");
  const sheet = document.getElementById("sheet");
  const sheetList = document.getElementById("sheet-list");
  const bar = document.querySelector(".bar");
  const statusEl = document.getElementById("status");
  const statusText = document.getElementById("status-text");
  const controls = [...document.querySelectorAll("[data-control]")];
  window.PJ.setLang("");
  function translate() {
    layoutsEl.setAttribute("aria-label", t("profile"));
    modeEl.setAttribute("aria-label", t("leftControl"));
    for (const el of document.querySelectorAll("[data-text]")) el.textContent = t(el.dataset.text);
  }
  translate();
  statusText.textContent = t("off");

  let stick = new Set();      // directions, plus the sprint control while sprinting
  let buttons = new Set();
  const pointers = new Map(); // pointerId -> control under that finger, or null
  let ws = null, lastPong = 0, lastSent = "";
  let build = null, stickSprint = "", haptics = true;

  // Android vibrates through navigator.vibrate. iPhone Safari has no such API, but iOS 18 taps the
  // Taptic Engine when the user toggles a switch checkbox, and only on a real tap: each button gets
  // an invisible one on top (how the ios-haptics library does it), so on iPhone it buzzes as the
  // finger lifts.
  const IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  if (IOS) {
    for (const el of controls) {
      const toggle = document.createElement("input");
      toggle.type = "checkbox";
      toggle.setAttribute("switch", "");
      toggle.className = "haptic";
      toggle.tabIndex = -1;
      toggle.setAttribute("aria-hidden", "true");
      el.append(toggle);
    }
  }
  function setHaptics(on) {
    haptics = on;
    document.body.classList.toggle("no-haptics", !on);
  }
  function buzz() {
    if (haptics && !IOS && navigator.vibrate) navigator.vibrate(12);
  }

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
    statusText.textContent = t(on ? "on" : "off");
  }, PING_MS);

  function applyConfig(msg) {
    if (build && msg.build !== build) return location.reload(); // the server restarted with new code
    build = msg.build;
    window.PJ.setLang(msg.lang);
    translate();
    document.body.dataset.style = msg.style;
    stickSprint = msg.stickSprint;
    setHaptics(msg.haptics !== false);
    renderProfiles(msg.layouts, msg.layout);
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

  // pointerup, not click: touchstart is cancelled below, so iOS never fires click.
  function profileButton(id, label, current, role = "radio") {
    const b = document.createElement("button");
    b.textContent = layoutLabel(id, label);
    b.setAttribute("role", role);
    b.setAttribute("aria-checked", String(id === current));
    b.addEventListener("pointerup", () => {
      sheet.hidden = true;
      if (isOpen() && id !== current) ws.send(JSON.stringify({ type: "layout", name: id }));
    });
    return b;
  }

  // All profiles side by side while they fit; otherwise the current one opens a list.
  function renderProfiles(layouts, current) {
    layoutsEl.classList.remove("compact");
    layoutsEl.replaceChildren(...layouts.map(({ id, label }) => profileButton(id, label, current)));
    sheetList.replaceChildren(...layouts.map(({ id, label }) => profileButton(id, label, current)));
    if (bar.scrollWidth <= bar.clientWidth + 1) return;
    const active = layouts.find((l) => l.id === current);
    const open = document.createElement("button");
    open.textContent = `${layoutLabel(active.id, active.label)} ▾`;
    open.setAttribute("aria-haspopup", "listbox");
    open.addEventListener("pointerup", () => { sheet.hidden = false; });
    layoutsEl.classList.add("compact");
    layoutsEl.replaceChildren(open);
  }
  sheet.addEventListener("pointerup", (e) => { if (e.target === sheet) sheet.hidden = true; });

  function setStick(next) {
    if (next.size === stick.size && [...next].every((d) => stick.has(d))) return;
    stick = next;
    render();
    send();
  }

  // Both left controls end here: x and y point right and up, 1 = the edge of the ring or pad.
  // 8 sectors of 45° (the same cones as the PES 6 Web d-pad), with hysteresis so edges don't flicker.
  function steer(x, y, reach) {
    const magnitude = Math.hypot(x, y);
    if (magnitude < (stick.size ? STICK_OFF : STICK_ON)) return setStick(new Set());
    const ux = x / magnitude, uy = y / magnitude;
    const next = new Set();
    const axis = (dir, v) => { if (v > (stick.has(dir) ? AXIS_OFF : AXIS_ON)) next.add(dir); };
    axis("right", ux); axis("left", -ux); axis("up", uy); axis("down", -uy);
    // Football mode: a little past the edge the run control goes down too (Xbox touch guide: actionThreshold).
    if (stickSprint && reach > (stick.has(stickSprint) ? SPRINT_OFF : SPRINT_ON)) next.add(stickSprint);
    setStick(next);
  }

  // Analog: a stick that appears where the thumb lands.
  let manager = null;
  function createStick() {
    const m = nipplejs.create({
      zone,
      mode: "dynamic",
      size: STICK_SIZE,
      fadeTime: 80,
      color: { front: "rgba(236, 238, 241, 0.9)", back: "rgba(236, 238, 241, 0.14)" },
    });
    m.on("start", () => zone.classList.add("active"));
    m.on("end", () => { zone.classList.remove("active"); setStick(new Set()); });
    m.on("move", (evt) => {
      const { x, y } = evt.data.vector;
      steer(x, y, evt.data.raw.distance / (STICK_SIZE / 2));
    });
    return m;
  }

  // D-pad: fixed in place; the whole left half reads the thumb relative to its center.
  let dpadPointer = null;
  function dpadMove(e) {
    const r = dpad.getBoundingClientRect(), half = r.width / 2;
    const x = (e.clientX - r.left - half) / half, y = (r.top + half - e.clientY) / half;
    steer(x, y, Math.hypot(x, y));
  }
  dpadZone.addEventListener("pointerdown", (e) => {
    if (dpadPointer !== null) return;
    dpadPointer = e.pointerId;
    dpadMove(e);
  });
  dpadZone.addEventListener("pointermove", (e) => { if (e.pointerId === dpadPointer) dpadMove(e); });
  for (const type of ["pointerup", "pointercancel"]) {
    dpadZone.addEventListener(type, (e) => {
      if (e.pointerId !== dpadPointer) return;
      dpadPointer = null;
      setStick(new Set());
    });
  }

  let mode = "dpad";
  try { mode = localStorage.getItem("pj.leftControl") === "analog" ? "analog" : "dpad"; } catch {}
  function setMode(next) {
    mode = next;
    try { localStorage.setItem("pj.leftControl", mode); } catch {}
    dpadPointer = null;
    stick = new Set();
    zone.hidden = mode !== "analog";
    dpadZone.hidden = mode !== "dpad";
    if (mode === "analog" && !manager) manager = createStick();
    if (mode === "dpad" && manager) { manager.destroy(); manager = null; }
    for (const b of modeEl.querySelectorAll("[data-mode]")) {
      b.setAttribute("aria-checked", String(b.dataset.mode === mode));
    }
    updateButtons();
  }
  for (const b of modeEl.querySelectorAll("[data-mode]")) {
    b.addEventListener("pointerup", () => { if (b.dataset.mode !== mode) setMode(b.dataset.mode); });
  }

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
    for (const arm of arms) arm.classList.toggle("pressed", stick.has(arm.dataset.dir));
    dpadZone.classList.toggle("sprint", stick.has(stickSprint));
    zone.classList.toggle("sprint", stick.has(stickSprint));
    for (const el of controls) {
      el.classList.toggle("pressed", buttons.has(el.dataset.control));
      el.classList.toggle("auto", stick.has(el.dataset.control));
    }
  }

  function updateButtons() {
    const before = buttons;
    buttons = new Set([...pointers.values()].filter(Boolean));
    if ([...buttons].some((b) => !before.has(b))) buzz();
    render();
    send();
  }

  document.addEventListener("pointerdown", (e) => {
    if ([zone, dpadZone, modeEl, layoutsEl, sheet].some((el) => el.contains(e.target))) return;
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
  // The iPhone vibration switches must get their tap, so their touches go through.
  document.addEventListener("touchstart", (e) => {
    if (!(haptics && e.target.classList.contains("haptic"))) e.preventDefault();
  }, { passive: false });
  document.addEventListener("touchmove", (e) => e.preventDefault(), { passive: false });
  document.addEventListener("gesturestart", (e) => e.preventDefault());
  document.addEventListener("contextmenu", (e) => e.preventDefault());

  setMode(mode);
  connect();
})();

(() => {
  "use strict";

  const PJ = window.PJ;
  const { t, keyLabel, layoutLabel } = PJ;

  const LETTERS = { a: "A", b: "B", x: "X", y: "Y" };
  const PLAYSTATION = { a: "✕", b: "○", x: "□", y: "△" };
  const STICK = {
    arrows: { up: "up", down: "down", left: "left", right: "right" },
    wasd: { up: "w", down: "s", left: "a", right: "d" },
  };
  const NEW_KEYS = { ...STICK.arrows, a: "space", b: "z", x: "x", y: "c", start: "enter", select: "escape" };
  const SPRINT_CONTROLS = ["r1", "l1", "a", "b", "x", "y", "start", "select"];
  const CODES = {
    ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right", Space: "space", Enter: "enter",
    Tab: "tab", Backspace: "backspace", Escape: "escape", ShiftLeft: "shift", ShiftRight: "shift",
  };
  // KeyboardEvent.code names the physical key, which is what the computer presses back.
  const keyFromCode = (code) => (/^Key[A-Z]$/.test(code) ? code[3].toLowerCase()
                                 : /^Digit\d$/.test(code) ? code[5] : CODES[code] || null);

  const $ = (id) => document.getElementById(id);
  const chips = [...document.querySelectorAll(".chip")];
  let layouts = {}, active = "", current = "", supported = new Set(), langChoice = "";
  let capturing = null, dirty = false, saving = false, saveTimer = null;

  function translate() {
    document.title = `Phone Joystick · ${t("title")}`;
    for (const el of document.querySelectorAll("[data-text]")) el.textContent = t(el.dataset.text);
    $("langs").setAttribute("aria-label", t("language"));
    $("profile-name").setAttribute("aria-label", t("profiles"));
    $("vibrate").addEventListener("change", async (e) => {
    try {
      load(await api("POST", "/api/settings", { haptics: e.target.checked }));
    } catch {
      setStatus(t("saveError"), true);
    }
  });

  for (const b of document.querySelectorAll("[data-lang]")) {
      b.setAttribute("aria-checked", String(b.dataset.lang === PJ.lang));
    }
  }
  PJ.setLang("");
  translate();

  async function api(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: { "X-Phone-Joystick": "setup", "Content-Type": "application/json" },
      body: body && JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  const layout = () => layouts[current];

  function controlName(control) {
    if (control in STICK.arrows) return t(control);
    if (control in LETTERS) return layout().names?.[control] || LETTERS[control];
    return { l1: "L1", r1: "R1", start: "Start", select: "Select" }[control];
  }

  function load(data) {
    layouts = data.layouts;
    active = data.active;
    langChoice = data.lang;
    $("vibrate").checked = data.haptics;
    PJ.setLang(data.lang);
    translate();
    supported = new Set(data.keys);
    if (!(current in layouts)) current = active;
    showPhones(data.phones);
    render();
  }

  function showPhones(n) {
    $("phones").dataset.state = n ? "on" : "off";
    $("phones-text").textContent = n == null ? t("serverDown") : n === 0 ? t("phones0") : n === 1 ? t("phones1") : t("phonesN", { n });
  }

  function setStatus(text, error = false) {
    $("save-status").textContent = text;
    $("save-status").classList.toggle("error", error);
  }

  function render() {
    const l = layout();
    $("profile-list").replaceChildren(...Object.entries(layouts).map(([id, profile]) => {
      const li = document.createElement("li");
      const b = document.createElement("button");
      b.className = "profile";
      if (id === current) b.setAttribute("aria-current", "true");
      const name = document.createElement("span");
      name.className = "profile-name";
      name.textContent = layoutLabel(id, profile.label);
      b.append(name);
      if (id === active) {
        const tag = document.createElement("span");
        tag.className = "tag";
        tag.textContent = t("inUse");
        b.append(tag);
      }
      b.addEventListener("click", () => { endCapture(); current = id; render(); });
      li.append(b);
      return li;
    }));

    const nameInput = $("profile-name");
    if (document.activeElement !== nameInput) nameInput.value = layoutLabel(current, l.label);
    $("in-use").hidden = current !== active;
    $("use-profile").hidden = current === active;
    $("delete").disabled = Object.keys(layouts).length < 2;

    $("device").dataset.style = l.style || "";
    for (const chip of chips) {
      const control = chip.dataset.control;
      const key = l.keys[control];
      chip.querySelector(".key").textContent = key ? keyLabel(key) : "—";
      chip.classList.toggle("empty", !key);
      chip.classList.toggle("capturing", control === capturing);
      chip.setAttribute("aria-label", `${controlName(control)}: ${key ? keyLabel(key) : t("noKey")}`);
      const name = chip.querySelector(".name");
      if (name && control in LETTERS) name.textContent = controlName(control);
    }

    for (const b of document.querySelectorAll("[data-stick]")) {
      const preset = STICK[b.dataset.stick];
      b.setAttribute("aria-pressed", String(Object.entries(preset).every(([c, k]) => l.keys[c] === k)));
    }
    for (const b of document.querySelectorAll("[data-style]")) {
      b.setAttribute("aria-checked", String((l.style || "") === b.dataset.style));
    }

    const runnable = SPRINT_CONTROLS.filter((c) => l.keys[c]);
    $("football").checked = Boolean(l.stickSprint);
    $("football").disabled = !runnable.length;
    $("run-row").hidden = !l.stickSprint;
    $("sprint").replaceChildren(...runnable.map((c) => new Option(`${controlName(c)} (${keyLabel(l.keys[c])})`, c)));
    $("sprint").value = l.stickSprint || "";
  }

  function changed() {
    dirty = true;
    render();
    setStatus(t("saving"));
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 300);
  }

  async function save() {
    saving = true;
    dirty = false;
    try {
      const data = await api("PUT", "/api/profiles", { layouts, active });
      showPhones(data.phones);
      setStatus(t("saved"));
    } catch {
      dirty = true;
      setStatus(t("saveError"), true);
    }
    saving = false;
  }

  // Picks up changes made from the phone (switching profile) and the phone count.
  async function poll() {
    if (dirty || saving || capturing) return;
    try {
      const data = await api("GET", "/api/profiles");
      if (data.active !== active || data.lang !== langChoice || data.haptics !== $("vibrate").checked
          || JSON.stringify(data.layouts) !== JSON.stringify(layouts)) load(data);
      else showPhones(data.phones);
    } catch {
      showPhones(null);
    }
  }

  function newId() {
    return `p${Date.now().toString(36)}`;
  }

  function uniqueName(name) {
    const taken = new Set(Object.entries(layouts).map(([id, l]) => layoutLabel(id, l.label)));
    let candidate = name.slice(0, 40), n = 2;
    while (taken.has(candidate)) candidate = `${name.slice(0, 36)} ${n++}`;
    return candidate;
  }

  function startCapture(control) {
    capturing = control;
    $("capture").hidden = false;
    $("capture-text").textContent = t("capture", { name: controlName(control) });
    $("capture-text").classList.remove("error");
    render();
  }

  function endCapture() {
    if (!capturing) return;
    capturing = null;
    $("capture").hidden = true;
    render();
  }

  function setKey(control, key) {
    const l = layout();
    if (key) l.keys[control] = key;
    else delete l.keys[control];
    if (l.stickSprint && !l.keys[l.stickSprint]) delete l.stickSprint;
    capturing = null;
    $("capture").hidden = true;
    changed();
  }

  window.addEventListener("keydown", (e) => {
    if (!capturing) return;
    e.preventDefault(); // Tab must not move the focus, Space must not scroll
    e.stopPropagation();
    const key = keyFromCode(e.code);
    if (key && supported.has(key) && !e.ctrlKey && !e.altKey && !e.metaKey) return setKey(capturing, key);
    const pressed = [e.ctrlKey && "Ctrl", e.altKey && "Alt", e.metaKey && "Cmd"].filter(Boolean);
    if (!pressed.length || !["Control", "Alt", "Meta"].includes(e.key)) pressed.push(e.key.length === 1 ? e.key.toUpperCase() : e.key);
    $("capture-text").textContent = t("notAllowed", { key: [...new Set(pressed)].join("+") });
    $("capture-text").classList.add("error");
  }, true);

  for (const chip of chips) chip.addEventListener("click", () => startCapture(chip.dataset.control));
  $("clear-key").addEventListener("click", () => setKey(capturing, null));
  $("cancel-capture").addEventListener("click", endCapture);
  document.addEventListener("click", (e) => {
    if (capturing && !e.target.closest(".chip, #capture")) endCapture();
  });

  $("profile-name").addEventListener("input", (e) => {
    const name = e.target.value.trim();
    if (!name) return;
    layout().label = name;
    changed();
  });
  $("profile-name").addEventListener("blur", render);

  $("use-profile").addEventListener("click", () => { active = current; changed(); });

  $("new-profile").addEventListener("click", () => {
    const id = newId();
    layouts[id] = { label: uniqueName(t("newName", { n: Object.keys(layouts).length + 1 })), keys: { ...NEW_KEYS } };
    current = id;
    changed();
    $("profile-name").focus();
    $("profile-name").select();
  });

  $("duplicate").addEventListener("click", () => {
    const id = newId();
    const copy = structuredClone(layout());
    copy.label = uniqueName(t("copy", { name: layoutLabel(current, copy.label) }));
    layouts[id] = copy;
    current = id;
    changed();
  });

  function confirm(text, ok) {
    $("confirm-text").textContent = text;
    $("confirm-ok").textContent = ok;
    $("confirm").returnValue = "";
    $("confirm").showModal();
    return new Promise((resolve) => {
      $("confirm").addEventListener("close", () => resolve($("confirm").returnValue === "ok"), { once: true });
    });
  }

  $("delete").addEventListener("click", async () => {
    const name = layoutLabel(current, layout().label);
    if (!(await confirm(t("confirmDelete", { name }), t("deleteOk")))) return;
    delete layouts[current];
    if (!(active in layouts)) active = Object.keys(layouts)[0];
    current = active;
    changed();
  });

  $("reset").addEventListener("click", async () => {
    if (!(await confirm(t("confirmReset"), t("resetOk")))) return;
    clearTimeout(saveTimer);
    try {
      load(await api("POST", "/api/profiles/reset"));
      current = active;
      render();
      setStatus(t("saved"));
    } catch {
      setStatus(t("saveError"), true);
    }
  });

  for (const b of document.querySelectorAll("[data-stick]")) {
    b.addEventListener("click", () => { Object.assign(layout().keys, STICK[b.dataset.stick]); changed(); });
  }
  for (const b of document.querySelectorAll("[data-style]")) {
    b.addEventListener("click", () => {
      const l = layout();
      if (b.dataset.style) Object.assign(l, { style: b.dataset.style, names: { ...PLAYSTATION } });
      else { delete l.style; delete l.names; }
      changed();
    });
  }
  $("football").addEventListener("change", (e) => {
    const l = layout();
    if (e.target.checked) l.stickSprint = l.keys.r1 ? "r1" : SPRINT_CONTROLS.find((c) => l.keys[c]);
    else delete l.stickSprint;
    changed();
  });
  $("sprint").addEventListener("change", (e) => { layout().stickSprint = e.target.value; changed(); });

  for (const b of document.querySelectorAll("[data-lang]")) {
    b.addEventListener("click", async () => {
      try {
        load(await api("POST", "/api/settings", { lang: b.dataset.lang }));
      } catch {
        setStatus(t("saveError"), true);
      }
    });
  }

  api("GET", "/api/profiles").then(load, () => showPhones(null));
  setInterval(poll, 2000);
})();

(() => {
  "use strict";

  const { lang, keyLabel, layoutLabel } = window.PJ;
  const T = {
    es: {
      title: "Controles", profiles: "Perfiles", newProfile: "Nuevo perfil", reset: "Volver a los perfiles de fábrica",
      inUse: "En uso", use: "Usar en el teléfono", stick: "Stick", arrows: "Flechas", buttons: "Botones",
      sprint: "Al llevar el stick más allá del aro, apretar también", nothing: "Nada",
      duplicate: "Duplicar", delete: "Borrar perfil", noKey: "Sin tecla", cancel: "Cancelar",
      capture: "Apretá la tecla para {name}", notAllowed: "{key} no se puede usar. Probá con otra tecla.",
      saving: "Guardando…", saved: "Guardado", saveError: "No se pudo guardar",
      phones0: "Ningún teléfono conectado", phones1: "1 teléfono conectado", phonesN: "{n} teléfonos conectados",
      serverDown: "Phone Joystick no está abierto",
      confirmDelete: "¿Borrar el perfil «{name}»?", confirmReset: "¿Volver a los perfiles de fábrica? Se pierden los perfiles y los cambios que hiciste.",
      deleteOk: "Borrar", resetOk: "Volver a los de fábrica", newName: "Perfil {n}", copy: "{name} (copia)",
      up: "stick arriba", down: "stick abajo", left: "stick a la izquierda", right: "stick a la derecha",
    },
    en: {
      title: "Controls", profiles: "Profiles", newProfile: "New profile", reset: "Go back to the built-in profiles",
      inUse: "In use", use: "Use on the phone", stick: "Stick", arrows: "Arrows", buttons: "Buttons",
      sprint: "When the stick goes past its ring, also press", nothing: "Nothing",
      duplicate: "Duplicate", delete: "Delete profile", noKey: "No key", cancel: "Cancel",
      capture: "Press the key for {name}", notAllowed: "{key} can't be used. Try another key.",
      saving: "Saving…", saved: "Saved", saveError: "Couldn't save",
      phones0: "No phone connected", phones1: "1 phone connected", phonesN: "{n} phones connected",
      serverDown: "Phone Joystick isn't running",
      confirmDelete: "Delete the “{name}” profile?", confirmReset: "Go back to the built-in profiles? Your profiles and changes will be lost.",
      deleteOk: "Delete", resetOk: "Go back to built-in", newName: "Profile {n}", copy: "{name} (copy)",
      up: "stick up", down: "stick down", left: "stick left", right: "stick right",
    },
  }[lang];
  const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, k) => values[k]);

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
  let layouts = {}, active = "", current = "", supported = new Set();
  let capturing = null, dirty = false, saving = false, saveTimer = null;

  document.documentElement.lang = lang;
  document.title = `Phone Joystick · ${T.title}`;
  for (const el of document.querySelectorAll("[data-text]")) el.textContent = T[el.dataset.text];

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
    if (control in STICK.arrows) return T[control];
    if (control in LETTERS) return layout().names?.[control] || LETTERS[control];
    return { l1: "L1", r1: "R1", start: "Start", select: "Select" }[control];
  }

  function load(data) {
    layouts = data.layouts;
    active = data.active;
    supported = new Set(data.keys);
    if (!(current in layouts)) current = active;
    showPhones(data.phones);
    render();
  }

  function showPhones(n) {
    $("phones").dataset.state = n ? "on" : "off";
    $("phones-text").textContent = n == null ? T.serverDown : n === 0 ? T.phones0 : n === 1 ? T.phones1 : fill(T.phonesN, { n });
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
        tag.textContent = T.inUse;
        b.append(tag);
      }
      b.addEventListener("click", () => { endCapture(); current = id; render(); });
      li.append(b);
      return li;
    }));

    const nameInput = $("profile-name");
    if (document.activeElement !== nameInput) nameInput.value = layoutLabel(current, l.label);
    nameInput.setAttribute("aria-label", T.profiles);
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
      chip.setAttribute("aria-label", `${controlName(control)}: ${key ? keyLabel(key) : T.noKey}`);
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

    const sprint = $("sprint");
    const options = [["", T.nothing], ...SPRINT_CONTROLS.filter((c) => l.keys[c])
      .map((c) => [c, `${controlName(c)} (${keyLabel(l.keys[c])})`])];
    sprint.replaceChildren(...options.map(([value, text]) => new Option(text, value)));
    sprint.value = l.stickSprint || "";
  }

  function changed() {
    dirty = true;
    render();
    setStatus(T.saving);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 300);
  }

  async function save() {
    saving = true;
    dirty = false;
    try {
      const data = await api("PUT", "/api/profiles", { layouts, active });
      showPhones(data.phones);
      setStatus(T.saved);
    } catch {
      dirty = true;
      setStatus(T.saveError, true);
    }
    saving = false;
  }

  // Picks up changes made from the phone (switching profile) and the phone count.
  async function poll() {
    if (dirty || saving || capturing) return;
    try {
      const data = await api("GET", "/api/profiles");
      if (data.active !== active || JSON.stringify(data.layouts) !== JSON.stringify(layouts)) load(data);
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
    $("capture-text").textContent = fill(T.capture, { name: controlName(control) });
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
    $("capture-text").textContent = fill(T.notAllowed, { key: [...new Set(pressed)].join("+") });
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
    layouts[id] = { label: uniqueName(fill(T.newName, { n: Object.keys(layouts).length + 1 })), keys: { ...NEW_KEYS } };
    current = id;
    changed();
    $("profile-name").focus();
    $("profile-name").select();
  });

  $("duplicate").addEventListener("click", () => {
    const id = newId();
    const copy = structuredClone(layout());
    copy.label = uniqueName(fill(T.copy, { name: layoutLabel(current, copy.label) }));
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
    if (!(await confirm(fill(T.confirmDelete, { name }), T.deleteOk))) return;
    delete layouts[current];
    if (!(active in layouts)) active = Object.keys(layouts)[0];
    current = active;
    changed();
  });

  $("reset").addEventListener("click", async () => {
    if (!(await confirm(T.confirmReset, T.resetOk))) return;
    clearTimeout(saveTimer);
    try {
      load(await api("POST", "/api/profiles/reset"));
      current = active;
      render();
      setStatus(T.saved);
    } catch {
      setStatus(T.saveError, true);
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
  $("sprint").addEventListener("change", (e) => {
    if (e.target.value) layout().stickSprint = e.target.value;
    else delete layout().stickSprint;
    changed();
  });

  api("GET", "/api/profiles").then(load, () => showPhones(null));
  setInterval(poll, 2000);
})();

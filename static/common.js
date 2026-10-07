// Texts and helpers shared by the phone page and the setup page.
window.PJ = (() => {
  const LANGS = ["es", "pt", "en"];
  const STRINGS = {
    es: {
      phoneSettings: "En el teléfono", vibrate: "Vibrar al tocar un botón",
      on: "Conectado", off: "Sin conexión", profile: "Perfil", key_space: "Espacio", key_backspace: "Borrar",
      arrows: "Flechas", language: "Idioma",
      title: "Configuración", profiles: "Perfiles", newProfile: "Nuevo perfil", reset: "Volver a los perfiles de fábrica",
      inUse: "En uso", use: "Usar en el teléfono", stick: "Stick", buttons: "Botones",
      football: "Modo fútbol",
      footballHelp: "En el teléfono cuesta apretar el botón de correr mientras movés el stick. Con el modo fútbol, cuando llevás el stick un poco más allá del borde de su círculo, el botón de correr se aprieta solo.",
      runButton: "Botón de correr", duplicate: "Duplicar", delete: "Borrar perfil", noKey: "Sin tecla", cancel: "Cancelar",
      capture: "Apretá la tecla para {name}", notAllowed: "{key} no se puede usar. Probá con otra tecla.",
      saving: "Guardando…", saved: "Guardado", saveError: "No se pudo guardar",
      phones0: "Ningún teléfono conectado", phones1: "1 teléfono conectado", phonesN: "{n} teléfonos conectados",
      serverDown: "Phone Joystick no está abierto",
      confirmDelete: "¿Borrar el perfil «{name}»?",
      confirmReset: "¿Volver a los perfiles de fábrica? Se pierden los perfiles y los cambios que hiciste.",
      deleteOk: "Borrar", resetOk: "Volver a los de fábrica", newName: "Perfil {n}", copy: "{name} (copia)",
      up: "stick arriba", down: "stick abajo", left: "stick a la izquierda", right: "stick a la derecha",
    },
    pt: {
      phoneSettings: "No celular", vibrate: "Vibrar ao tocar um botão",
      on: "Conectado", off: "Sem conexão", profile: "Perfil", key_space: "Espaço", key_backspace: "Apagar",
      arrows: "Setas", language: "Idioma",
      title: "Configuração", profiles: "Perfis", newProfile: "Novo perfil", reset: "Voltar aos perfis originais",
      inUse: "Em uso", use: "Usar no celular", stick: "Analógico", buttons: "Botões",
      football: "Modo futebol",
      footballHelp: "No celular é difícil apertar o botão de correr enquanto você move o analógico. Com o modo futebol, quando você leva o analógico um pouco além da borda do círculo, o botão de correr é apertado sozinho.",
      runButton: "Botão de correr", duplicate: "Duplicar", delete: "Apagar perfil", noKey: "Sem tecla", cancel: "Cancelar",
      capture: "Aperte a tecla para {name}", notAllowed: "{key} não pode ser usada. Tente outra tecla.",
      saving: "Salvando…", saved: "Salvo", saveError: "Não foi possível salvar",
      phones0: "Nenhum celular conectado", phones1: "1 celular conectado", phonesN: "{n} celulares conectados",
      serverDown: "O Phone Joystick não está aberto",
      confirmDelete: "Apagar o perfil “{name}”?",
      confirmReset: "Voltar aos perfis originais? Os perfis e as mudanças que você fez serão perdidos.",
      deleteOk: "Apagar", resetOk: "Voltar aos originais", newName: "Perfil {n}", copy: "{name} (cópia)",
      up: "analógico para cima", down: "analógico para baixo", left: "analógico para a esquerda",
      right: "analógico para a direita",
    },
    en: {
      phoneSettings: "On the phone", vibrate: "Vibrate when you tap a button",
      on: "Connected", off: "Disconnected", profile: "Profile", key_space: "Space", key_backspace: "Backspace",
      arrows: "Arrows", language: "Language",
      title: "Setup", profiles: "Profiles", newProfile: "New profile", reset: "Go back to the built-in profiles",
      inUse: "In use", use: "Use on the phone", stick: "Stick", buttons: "Buttons",
      football: "Football mode",
      footballHelp: "On a phone it's hard to hold the run button while you move the stick. In football mode, pushing the stick a little past the edge of its circle presses the run button for you.",
      runButton: "Run button", duplicate: "Duplicate", delete: "Delete profile", noKey: "No key", cancel: "Cancel",
      capture: "Press the key for {name}", notAllowed: "{key} can't be used. Try another key.",
      saving: "Saving…", saved: "Saved", saveError: "Couldn't save",
      phones0: "No phone connected", phones1: "1 phone connected", phonesN: "{n} phones connected",
      serverDown: "Phone Joystick isn't running",
      confirmDelete: "Delete the “{name}” profile?",
      confirmReset: "Go back to the built-in profiles? Your profiles and changes will be lost.",
      deleteOk: "Delete", resetOk: "Go back to built-in", newName: "Profile {n}", copy: "{name} (copy)",
      up: "stick up", down: "stick down", left: "stick left", right: "stick right",
    },
  };
  const KEY_LABELS = { enter: "Enter", escape: "Esc", tab: "Tab", shift: "Shift", up: "↑", down: "↓", left: "←", right: "→" };
  const BUILTIN_LABELS = { arrows: "Arrows" }; // shipped names that are translated until someone renames them

  function detect() {
    const browser = navigator.language.toLowerCase();
    return LANGS.find((l) => browser.startsWith(l)) || "en";
  }

  let lang = detect();

  return {
    LANGS,
    get lang() { return lang; },
    // "" (or anything unknown) means: follow the device language.
    setLang(choice) {
      lang = LANGS.includes(choice) ? choice : detect();
      document.documentElement.lang = lang;
    },
    t: (key, values = {}) => (STRINGS[lang][key] ?? STRINGS.en[key]).replace(/\{(\w+)\}/g, (_, k) => values[k]),
    keyLabel: (key) => STRINGS[lang][`key_${key}`] || KEY_LABELS[key] || key.toUpperCase(),
    layoutLabel: (id, label) => (BUILTIN_LABELS[id] === label ? STRINGS[lang][id] : label),
  };
})();

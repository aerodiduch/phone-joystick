// Shared by the phone page and the setup page.
window.PJ = (() => {
  const lang = navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
  const KEY_LABELS = {
    ...{ es: { space: "Espacio", backspace: "Borrar" }, en: { space: "Space", backspace: "Backspace" } }[lang],
    enter: "Enter", escape: "Esc", tab: "Tab", shift: "Shift", up: "↑", down: "↓", left: "←", right: "→",
  };
  // Shipped profile names that are translated, as long as nobody renamed them.
  const BUILTIN = { arrows: { label: "Arrows", es: "Flechas", en: "Arrows" } };
  return {
    lang,
    keyLabel: (key) => KEY_LABELS[key] || key.toUpperCase(),
    layoutLabel: (id, label) => (BUILTIN[id]?.label === label ? BUILTIN[id][lang] : label),
  };
})();

(() => {
  const allowed = new Set(["sunset"]);
  let selected = "sunset";
  try {
    const version = localStorage.getItem("vishap_palette_version");
    const saved = localStorage.getItem("vishap_palette");
    if (version === "2" && allowed.has(saved)) selected = saved;
    else {
      localStorage.setItem("vishap_palette", selected);
      localStorage.setItem("vishap_palette_version", "2");
    }
  } catch (_) {
    // The default palette still works when browser storage is unavailable.
  }
  document.documentElement.dataset.palette = selected;
})();

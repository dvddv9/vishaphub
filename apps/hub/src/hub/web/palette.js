(() => {
  const allowed = new Set(["violet", "ocean", "sunset"]);
  let selected = "violet";
  try {
    const saved = localStorage.getItem("vishap_palette");
    if (allowed.has(saved)) selected = saved;
  } catch (_) {
    // The default palette still works when browser storage is unavailable.
  }
  document.documentElement.dataset.palette = selected;
})();

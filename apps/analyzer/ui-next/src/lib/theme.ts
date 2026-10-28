export type Theme = "dark" | "light";

export const THEME_KEY = "vishap.theme";
/** Dark is the default; the light theme is an opt-in. */
export const DEFAULT_THEME: Theme = "dark";

/**
 * Runs in <head> before the first paint so a stored "light" choice never flashes dark.
 * Storage can be blocked (private windows, embedded webviews), hence the try/catch.
 */
export const THEME_INIT_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t}}catch(e){}`;

export function readTheme(): Theme {
  if (typeof document === "undefined") return DEFAULT_THEME;
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* storage unavailable: the choice lasts until the page closes */
  }
}

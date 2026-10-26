/**
 * The caller's own LLM choice (provider, model, API key), kept in this browser
 * only and sent per request. Shared by the upload form and the settings panel.
 *
 * The API key is the sensitive part. By default it lives in sessionStorage, so it
 * is gone when the tab / browser closes. "Remember on this device" is an explicit
 * opt-in that moves it to localStorage (readable by any script on this origin and
 * kept until removed). Provider and model are not secret and always persist.
 */
export const LLM_CHANGED = "vishap-llm-changed";

export interface LlmChoice {
  key: string;
  provider: string;
  model: string;
}

const KEY_NAME = "llmApiKey";
const REMEMBER_NAME = "llmRememberKey";
const PLAIN_NAMES = { provider: "llmProvider", model: "llmModel" } as const;

function safe<T>(fn: () => T, fallback: T): T {
  try {
    return fn();
  } catch {
    /* storage unavailable (SSR, private mode, blocked): behave as empty */
    return fallback;
  }
}

/** True when the key is (or should be) kept in localStorage. Older installs that
 *  already have a key there stay "remembered" until the user unticks it. */
export function readRemember(): boolean {
  return safe(
    () => localStorage.getItem(REMEMBER_NAME) === "1" || localStorage.getItem(KEY_NAME) !== null,
    false,
  );
}

export function readLlmChoice(): LlmChoice {
  return {
    key: safe(() => sessionStorage.getItem(KEY_NAME) ?? localStorage.getItem(KEY_NAME) ?? "", ""),
    provider: safe(() => localStorage.getItem(PLAIN_NAMES.provider) ?? "", ""),
    model: safe(() => localStorage.getItem(PLAIN_NAMES.model) ?? "", ""),
  };
}

function storeKey(key: string, remember: boolean): void {
  safe(() => {
    sessionStorage.removeItem(KEY_NAME);
    localStorage.removeItem(KEY_NAME);
    if (!key) return;
    (remember ? localStorage : sessionStorage).setItem(KEY_NAME, key);
  }, undefined);
}

/** Switch where the current key is kept (also remembers the choice). */
export function writeRemember(remember: boolean): void {
  safe(() => {
    if (remember) localStorage.setItem(REMEMBER_NAME, "1");
    else localStorage.removeItem(REMEMBER_NAME);
  }, undefined);
  storeKey(readLlmChoice().key, remember);
  if (typeof window !== "undefined") window.dispatchEvent(new Event(LLM_CHANGED));
}

export function writeLlmChoice(patch: Partial<LlmChoice>): void {
  if (patch.key !== undefined) storeKey(patch.key, readRemember());
  (["provider", "model"] as const).forEach((field) => {
    if (patch[field] === undefined) return;
    const value = patch[field] ?? "";
    safe(() => {
      if (value) localStorage.setItem(PLAIN_NAMES[field], value);
      else localStorage.removeItem(PLAIN_NAMES[field]);
    }, undefined);
  });
  if (typeof window !== "undefined") window.dispatchEvent(new Event(LLM_CHANGED));
}

/**
 * The caller's own LLM choice (provider, model, API key), kept in this browser
 * only and sent per request. Shared by the upload form and the settings panel.
 */
export const LLM_CHANGED = "vishap-llm-changed";

export interface LlmChoice {
  key: string;
  provider: string;
  model: string;
}

const STORAGE_NAMES: Record<keyof LlmChoice, string> = {
  key: "llmApiKey",
  provider: "llmProvider",
  model: "llmModel",
};

export function readLlmChoice(): LlmChoice {
  const choice: LlmChoice = { key: "", provider: "", model: "" };
  try {
    (Object.keys(STORAGE_NAMES) as (keyof LlmChoice)[]).forEach((field) => {
      choice[field] = localStorage.getItem(STORAGE_NAMES[field]) ?? "";
    });
  } catch {
    /* storage unavailable (SSR, private mode): empty choice */
  }
  return choice;
}

export function writeLlmChoice(patch: Partial<LlmChoice>): void {
  try {
    (Object.keys(patch) as (keyof LlmChoice)[]).forEach((field) => {
      const value = patch[field] ?? "";
      if (value) localStorage.setItem(STORAGE_NAMES[field], value);
      else localStorage.removeItem(STORAGE_NAMES[field]);
    });
  } catch {
    /* storage unavailable: the choice lives only in component state */
  }
  if (typeof window !== "undefined") window.dispatchEvent(new Event(LLM_CHANGED));
}

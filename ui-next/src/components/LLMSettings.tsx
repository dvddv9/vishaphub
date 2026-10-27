"use client";

import { useEffect, useState } from "react";
import { apiFetch, getProviders, type LlmProvider } from "@/lib/api";
import { LLM_CHANGED, readLlmChoice, writeLlmChoice } from "@/lib/llmChoice";
import LlmKeyField from "@/components/LlmKeyField";

type Config = {
  locked?: boolean;
  server_key_only?: boolean;
  provider: string;
  custom_url: string;
  custom_model: string;
  has_custom_key: boolean;
};

const FIELD =
  "w-full mb-3 rounded border border-slate-300 bg-white p-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500";

/**
 * Public deployments: the server's LLM settings belong to the operator, so this
 * panel only stores the visitor's own provider / model / key in this browser.
 */
function UserKeySettings() {
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const choice = readLlmChoice();
    setProvider(choice.provider);
    setModel(choice.model);
    setKey(choice.key);
    getProviders()
      .then((list) => setProviders(list.providers))
      .catch((e: unknown) =>
        setMsg(`Could not load providers: ${e instanceof Error ? e.message : String(e)}`),
      );
    function sync() {
      const next = readLlmChoice();
      setProvider(next.provider);
      setModel(next.model);
      setKey(next.key);
    }
    window.addEventListener(LLM_CHANGED, sync);
    return () => window.removeEventListener(LLM_CHANGED, sync);
  }, []);

  function save() {
    if (!provider) {
      setMsg("Pick a provider.");
      return;
    }
    if (!key.trim()) {
      setMsg("Enter your API key.");
      return;
    }
    writeLlmChoice({ provider, model: model.trim(), key: key.trim() });
    setMsg("Saved. Your next analysis uses this provider and key.");
  }

  function clear() {
    writeLlmChoice({ provider: "", model: "", key: "" });
    setMsg("Removed from this browser.");
  }

  const current = providers.find((p) => p.id === provider);

  return (
    <div className="rounded-xl border border-slate-300 bg-white p-6 mt-8">
      <h2 className="text-lg font-semibold text-slate-900 mb-1">LLM provider</h2>
      <p className="mb-4 text-sm text-slate-600">
        This server does not use its own LLM key. Pick a provider and enter your key; it is
        stored in this browser only and sent with each analysis. Without a key Vishap still
        runs its built-in rules (no LLM), so you always get a report.
      </p>

      <label className="block text-sm text-slate-700 mb-1" htmlFor="user-llm-provider">
        Provider
      </label>
      <select
        id="user-llm-provider"
        className={FIELD}
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
      >
        <option value="">Select a provider…</option>
        {providers.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>

      <label className="block text-sm text-slate-700 mb-1" htmlFor="user-llm-model">
        Model (optional)
      </label>
      <input
        id="user-llm-model"
        className={FIELD}
        value={model}
        onChange={(e) => setModel(e.target.value)}
        placeholder={current?.default_model ?? "provider default"}
      />

      <label className="block text-sm text-slate-700 mb-1" htmlFor="user-llm-key">
        API key
      </label>
      <div className="mb-3">
        <LlmKeyField id="user-llm-key" value={key} onChange={setKey} className={FIELD} />
      </div>

      <div className="mt-2 flex gap-3">
        <button
          onClick={save}
          className="min-h-11 rounded bg-sky-500 px-4 py-2 font-semibold text-slate-950 hover:bg-sky-400 sm:min-h-10"
        >
          Save
        </button>
        <button
          onClick={clear}
          className="min-h-11 rounded border border-slate-300 px-4 py-2 text-slate-700 hover:bg-slate-100 sm:min-h-10"
        >
          Remove
        </button>
      </div>

      {msg && <p className="mt-2 text-sm text-slate-700">{msg}</p>}
    </div>
  );
}

/** Local / desktop installs: edits the backend's own LLM settings. */
function ServerSettings({ initial }: { initial: Config }) {
  const [cfg, setCfg] = useState<Config>(initial);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      await apiFetch("/llm/config", {
        method: "POST",
        body: JSON.stringify({
          provider: cfg.provider,
          custom_url: cfg.custom_url,
          custom_model: cfg.custom_model,
          custom_key: key || undefined,
        }),
      });
      setMsg("Saved!");
      setKey("");
    } catch (e: unknown) {
      setMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  }

  function pick(v: string) {
    const next = { ...cfg, provider: v };
    if (v === "anthropic") {
      next.custom_url = "https://api.anthropic.com/v1/";
      next.custom_model = "claude-sonnet-5-5";
    }
    if (v === "android") {
      next.custom_url = "https://generativelanguage.googleapis.com/v1beta/openai/";
      next.custom_model = "gemini-2.0-flash";
    }
    if (v === "groq") {
      next.custom_url = "https://api.groq.com/openai/v1";
      next.custom_model = "llama-3.3-70b-versatile";
    }
    if (v === "openai") {
      next.custom_url = "https://api.openai.com/v1";
      next.custom_model = "gpt-4o-mini";
    }
    if (v === "ollama") {
      next.custom_url = "http://127.0.0.1:11434/v1";
      next.custom_model = "llama3.1";
    }
    if (v === "custom") {
      next.custom_url = "https://api.anthropic.com/v1";
      next.custom_model = "claude-haiku-5-5";
    }
    setCfg(next);
  }

  return (
    <div className="rounded-xl border border-slate-300 bg-white p-6 mt-8">
      <h2 className="text-lg font-semibold text-slate-900 mb-4">LLM Provider</h2>

      <label className="block text-sm text-slate-700 mb-1">Provider</label>
      <select className={FIELD} value={cfg.provider} onChange={(e) => pick(e.target.value)}>
        <option value="custom">custom (Claude)</option>
        <option value="openai">OpenAI</option>
        <option value="groq">Groq</option>
        <option value="ollama">Ollama (local)</option>
        <option value="anthropic">Anthropic (Claude)</option>
        <option value="android">Android (OpenAI-compatible)</option>
      </select>

      {(cfg.provider === "custom" || cfg.provider === "anthropic" || cfg.provider === "android") && (
        <>
          <label className="block text-sm text-slate-700 mb-1">Base URL</label>
          <input
            className={FIELD}
            value={cfg.custom_url}
            onChange={(e) => setCfg({ ...cfg, custom_url: e.target.value })}
            placeholder="https://api.groq.com/openai/v1"
          />

          <label className="block text-sm text-slate-700 mb-1">Model</label>
          <input
            className={FIELD}
            value={cfg.custom_model}
            onChange={(e) => setCfg({ ...cfg, custom_model: e.target.value })}
            placeholder="llama-3.3-70b-versatile"
          />

          <label className="block text-sm text-slate-700 mb-1">
            API Key {cfg.has_custom_key && <span className="text-emerald-700">(already set)</span>}
          </label>
          <input
            type="password"
            className={FIELD}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="gsk_..."
          />
        </>
      )}

      <button
        onClick={save}
        disabled={saving}
        className="mt-2 min-h-11 rounded bg-sky-500 px-4 py-2 font-semibold text-slate-950 hover:bg-sky-400 disabled:opacity-50 sm:min-h-10"
      >
        {saving ? "Saving..." : "Save"}
      </button>

      {msg && <p className="mt-2 text-sm text-slate-700">{msg}</p>}
    </div>
  );
}

export default function LLMSettings() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<Config>("/llm/config")
      .then(setCfg)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  if (error) return <div className="mt-8 text-sm text-red-700">LLM settings: {error}</div>;
  if (!cfg) return <div className="text-slate-600">Loading LLM settings...</div>;
  if (cfg.server_key_only) {
    return (
      <div className="rounded-xl border border-slate-300 bg-white p-6 mt-8">
        <h2 className="text-lg font-semibold text-slate-900 mb-1">LLM</h2>
        <p className="text-sm text-slate-600">
          This server analyses with its built-in model. No provider or API key is needed.
        </p>
      </div>
    );
  }
  return cfg.locked ? <UserKeySettings /> : <ServerSettings initial={cfg} />;
}

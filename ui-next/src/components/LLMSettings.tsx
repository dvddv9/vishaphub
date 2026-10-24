"use client";

import { useEffect, useState } from "react";

type Config = {
  provider: string;
  custom_url: string;
  custom_model: string;
  has_custom_key: boolean;
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080";

export default function LLMSettings() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch(`${API}/llm/config`)
      .then((r) => r.json())
      .then(setCfg)
      .catch((e) => setMsg(`Load failed: ${e}`));
  }, []);

  async function save() {
    if (!cfg) return;
    setSaving(true);
    setMsg("");
    try {
      const r = await fetch(`${API}/llm/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: cfg.provider,
          custom_url: cfg.custom_url,
          custom_model: cfg.custom_model,
          custom_key: key || undefined,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      setMsg("Saved!");
      setKey("");
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  if (!cfg) return <div className="text-slate-600">Loading LLM settings...</div>;

  return (
    <div className="rounded-xl border border-slate-300 bg-white p-6 mt-8">
      <h2 className="text-lg font-semibold text-white mb-4">LLM Provider</h2>

      <label className="block text-sm text-slate-700 mb-1">Provider</label>
      <select
        className="w-full mb-3 rounded border border-slate-300 bg-white p-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        value={cfg.provider}
        onChange={(e) => {
          const v = e.target.value;
          const next = { ...cfg, provider: v };
          if (v === "anthropic") {
            next.custom_url   = "https://api.anthropic.com/v1/";
            next.custom_model = "claude-sonnet-4-20250514";
          }
          if (v === "android") {
            next.custom_url   = "https://generativelanguage.googleapis.com/v1beta/openai/";
            next.custom_model = "gemini-2.0-flash";
          }
          if (v === "groq") {
            next.custom_url   = "https://api.groq.com/openai/v1";
            next.custom_model = "llama-3.3-70b-versatile";
          }
          if (v === "openai") {
            next.custom_url   = "https://api.openai.com/v1";
            next.custom_model = "gpt-4o-mini";
          }
          if (v === "ollama") {
            next.custom_url   = "http://127.0.0.1:11434/v1";
            next.custom_model = "llama3.1";
          }
          if (v === "custom") {
            next.custom_url   = "https://api.deepseek.com/v1";
            next.custom_model = "deepseek-chat";
          }
          setCfg(next);
        }}
      >
        <option value="custom">custom (DeepSeek)</option>
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
            className="w-full mb-3 rounded border border-slate-300 bg-white p-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            value={cfg.custom_url}
            onChange={(e) => setCfg({ ...cfg, custom_url: e.target.value })}
            placeholder="https://api.groq.com/openai/v1"
          />

          <label className="block text-sm text-slate-700 mb-1">Model</label>
          <input
            className="w-full mb-3 rounded border border-slate-300 bg-white p-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            value={cfg.custom_model}
            onChange={(e) => setCfg({ ...cfg, custom_model: e.target.value })}
            placeholder="llama-3.3-70b-versatile"
          />

          <label className="block text-sm text-slate-700 mb-1">
            API Key {cfg.has_custom_key && <span className="text-green-400">(already set)</span>}
          </label>
          <input
            type="password"
            className="w-full mb-3 rounded border border-slate-300 bg-white p-2 text-slate-900 shadow-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="gsk_..."
          />
        </>
      )}

      <button
        onClick={save}
        disabled={saving}
        className="mt-2 rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-500 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save"}
      </button>

      {msg && <p className="mt-2 text-sm text-slate-700">{msg}</p>}
    </div>
  );
}

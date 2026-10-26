"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { FileUp, LoaderCircle, Sparkles, TriangleAlert } from "lucide-react";
import { rememberJob, submitAnalysis, getProviders, type LlmProvider } from "@/lib/api";

const ACCEPTED_EXTENSIONS = [".py", ".java", ".c", ".txt", ".md"];
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");
const MAX_BYTES = 2 * 1024 * 1024;

/**
 * A deliberately insecure snippet: it exercises the taint path (request.args →
 * execute) so a first run produces a report worth reading.
 */
const EXAMPLE_FILENAME = "example_sqli.py";
const EXAMPLE_MATERIAL = `import sqlite3

from flask import Flask, request

app = Flask(__name__)


@app.route("/user")
def user():
    name = request.args["name"]  # tainted: comes straight from the query string
    conn = sqlite3.connect("app.db")
    # SQL injection: the query is built by string formatting
    row = conn.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchone()
    return {"user": row}
`;

export default function UploadForm({ onSubmitted }: { onSubmitted: (jobId: string) => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [material, setMaterial] = useState("");
  const [filename, setFilename] = useState("pasted.txt");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [llmKey, setLlmKey] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("llmApiKey") ?? "";
  });
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [llmProvider, setLlmProvider] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("llmProvider") ?? "";
  });
  const [llmModel, setLlmModel] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("llmModel") ?? "";
  });

  useEffect(() => {
    let cancelled = false;
    getProviders()
      .then((list) => {
        if (!cancelled) setProviders(list);
      })
      .catch(() => {
        /* older server without /providers: the server default is used */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function remember(name: string, value: string) {
    try {
      if (value) localStorage.setItem(name, value);
      else localStorage.removeItem(name);
    } catch {
      /* storage unavailable: kept in memory only */
    }
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);

    if (file.size > MAX_BYTES) {
      setError(`File is larger than ${MAX_BYTES / (1024 * 1024)} MB.`);
      event.target.value = "";
      return;
    }

    const lower = file.name.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
      setError(`Unsupported file type. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`);
      event.target.value = "";
      return;
    }

    try {
      setMaterial(await file.text());
      setFilename(file.name);
    } catch {
      setError("Could not read the selected file.");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;

    if (!material.trim()) {
      setError("Paste some material or choose a file first.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const safeName = filename.trim() || "pasted.txt";
      const created = await submitAnalysis(
        material,
        safeName,
        llmKey || undefined,
        llmKey ? llmProvider || undefined : undefined,
        llmKey ? llmModel || undefined : undefined,
      );
      rememberJob({
        job_id: created.job_id,
        status: created.status,
        filename: safeName,
        created_at: new Date().toISOString(),
        started_at: null,
        finished_at: null,
        error: null,
      });
      onSubmitted(created.job_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unexpected error while submitting.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label
          htmlFor="material-file"
          className="text-sm font-medium text-slate-300"
        >
          Upload a file
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <input
            id="material-file"
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_ATTR}
            onChange={handleFileChange}
            disabled={submitting}
            className="block w-full max-w-sm cursor-pointer rounded-lg border border-slate-700 bg-slate-900/60 p-2 text-sm text-slate-300 file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-slate-700 file:px-3 file:py-1.5 file:text-sm file:text-slate-100 hover:file:bg-slate-600"
          />
          <span className="text-xs text-slate-500">
            {ACCEPTED_EXTENSIONS.join(" · ")} · max 2 MB
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label htmlFor="material-text" className="text-sm font-medium text-slate-300">
            …or paste the material
          </label>
          <span className="font-mono text-xs text-slate-500">
            {material.length.toLocaleString()} chars
          </span>
        </div>
        <textarea
          id="material-text"
          value={material}
          onChange={(event) => setMaterial(event.target.value)}
          disabled={submitting}
          spellCheck={false}
          placeholder="Paste code, config, spec, logs or data here…"
          className="terminal min-h-72 w-full resize-y outline-none focus:border-sky-600"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="material-name" className="text-sm font-medium text-slate-300">
          Filename (used as analysis context)
        </label>
        <input
          id="material-name"
          type="text"
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          disabled={submitting}
          className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 font-mono text-sm text-slate-200 outline-none focus:border-sky-600"
        />
      </div>

      <div className="flex flex-col gap-2">
        {providers.length > 0 ? (
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="llm-provider" className="text-sm font-medium text-slate-300">
                LLM provider
              </label>
              <select
                id="llm-provider"
                value={llmProvider}
                onChange={(event) => {
                  setLlmProvider(event.target.value);
                  remember("llmProvider", event.target.value);
                }}
                disabled={submitting}
                className="rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 text-sm text-slate-200 outline-none focus:border-sky-600"
              >
                <option value="">Server default</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="llm-model" className="text-sm font-medium text-slate-300">
                Model (optional)
              </label>
              <input
                id="llm-model"
                type="text"
                value={llmModel}
                onChange={(event) => {
                  const value = event.target.value.trim();
                  setLlmModel(value);
                  remember("llmModel", value);
                }}
                disabled={submitting}
                placeholder={
                  providers.find((p) => p.id === llmProvider)?.default_model ?? "provider default"
                }
                className="w-64 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 font-mono text-sm text-slate-200 outline-none focus:border-sky-600"
              />
            </div>
          </div>
        ) : null}
        <label htmlFor="llm-key" className="text-sm font-medium text-slate-300">
          Your LLM API key
        </label>
        <input
          id="llm-key"
          type="password"
          autoComplete="off"
          value={llmKey}
          onChange={(event) => {
            const value = event.target.value.trim();
            setLlmKey(value);
            try {
              if (value) localStorage.setItem("llmApiKey", value);
              else localStorage.removeItem("llmApiKey");
            } catch {
              /* storage unavailable: the key lives only in memory */
            }
          }}
          disabled={submitting}
          placeholder="sk-…"
          className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2 font-mono text-sm text-slate-200 outline-none focus:border-sky-600"
        />
        <p className="text-xs text-slate-500">
          Sent over HTTPS to this Vishap server, which forwards it only to the provider you
          picked, for your analysis. Stored in this browser only; clear the field to remove it.
        </p>
      </div>

      {error ? (
        <p className="flex items-start gap-2 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting || !material.trim()}
          className="inline-flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {submitting ? (
            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <FileUp className="h-4 w-4" aria-hidden="true" />
          )}
          {submitting ? "Submitting…" : "Analyze"}
        </button>
        <button
          type="button"
          onClick={() => {
            setMaterial("");
            setFilename("pasted.txt");
            setError(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
          disabled={submitting}
          className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100 disabled:opacity-50"
        >
          Clear
        </button>
        <button
          type="button"
          onClick={() => {
            setMaterial(EXAMPLE_MATERIAL);
            setFilename(EXAMPLE_FILENAME);
            setError(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
          disabled={submitting}
          title="Fill the form with a small vulnerable Python snippet"
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 transition-colors hover:border-sky-600 hover:text-sky-300 disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Load example
        </button>
      </div>
    </form>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { FileUp, LoaderCircle, Sparkles, TriangleAlert } from "lucide-react";
import { rememberJob, submitAnalysis, getProviders, type LlmProvider } from "@/lib/api";
import { LLM_CHANGED, readLlmChoice, writeLlmChoice } from "@/lib/llmChoice";
import LlmKeyField from "@/components/LlmKeyField";

const ACCEPTED_EXTENSIONS = [
  ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h", ".cpp", ".go", ".php",
  ".tf", ".yaml", ".yml", ".json", ".sql", ".sh", ".log", ".txt", ".md",
];
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");
/** The API rejects anything over 200,000 characters (HTTP 422), so stop it here. */
const MAX_CHARS = 200_000;

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

export interface UploadDraft {
  material: string;
  filename: string;
}

export default function UploadForm({
  onSubmitted,
  initial,
}: {
  onSubmitted: (jobId: string, draft: UploadDraft) => void;
  /** Prefill (used to retry after the server lost a job). */
  initial?: UploadDraft | null;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [material, setMaterial] = useState(initial?.material ?? "");
  const [filename, setFilename] = useState(initial?.filename ?? "pasted.txt");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [llmKey, setLlmKey] = useState<string>(() => readLlmChoice().key);
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [llmProvider, setLlmProvider] = useState<string>(() => readLlmChoice().provider);
  const [llmModel, setLlmModel] = useState<string>(() => readLlmChoice().model);
  const [requiresUserKey, setRequiresUserKey] = useState(false);
  const rulesOnly = requiresUserKey && !llmKey;

  useEffect(() => {
    let cancelled = false;
    getProviders()
      .then((list) => {
        if (cancelled) return;
        setProviders(list.providers);
        setRequiresUserKey(list.requiresUserKey);
      })
      .catch(() => {
        /* older server without /providers: the server default is used */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // "Try example (SQLi)" links here with ?example=sqli: prefill the form once.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("example") === "sqli") {
      setMaterial((current) => current || EXAMPLE_MATERIAL);
      setFilename((current) => (current === "pasted.txt" ? EXAMPLE_FILENAME : current));
    }
  }, []);

  // The settings panel edits the same browser-side choice; stay in sync with it.
  useEffect(() => {
    function sync() {
      const choice = readLlmChoice();
      setLlmKey(choice.key);
      setLlmProvider(choice.provider);
      setLlmModel(choice.model);
    }
    window.addEventListener(LLM_CHANGED, sync);
    return () => window.removeEventListener(LLM_CHANGED, sync);
  }, []);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);

    // generous byte pre-check (UTF-8 can be 4 bytes/char); the exact limit is in characters
    if (file.size > MAX_CHARS * 4) {
      setError(`File is too large. Limit: ${MAX_CHARS.toLocaleString()} characters.`);
      event.target.value = "";
      return;
    }

    const lower = file.name.toLowerCase();
    const isDockerfile = lower === "dockerfile" || lower.startsWith("dockerfile.");
    if (!isDockerfile && !ACCEPTED_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
      setError(`Unsupported file type. Accepted: ${ACCEPTED_EXTENSIONS.join(", ")}`);
      event.target.value = "";
      return;
    }

    try {
      const text = await file.text();
      if (text.length > MAX_CHARS) {
        setError(
          `File has ${text.length.toLocaleString()} characters; the limit is ${MAX_CHARS.toLocaleString()}. Split it into smaller parts.`,
        );
        event.target.value = "";
        return;
      }
      setMaterial(text);
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
    if (material.length > MAX_CHARS) {
      setError(
        `Material has ${material.length.toLocaleString()} characters; the limit is ${MAX_CHARS.toLocaleString()}.`,
      );
      return;
    }
    if (llmProvider && !llmKey) {
      setError("You picked an LLM provider but entered no key. Add the key, or set the provider back to the no-key option.");
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
      onSubmitted(created.job_id, { material, filename: safeName });
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
          className="text-sm font-medium text-slate-700"
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
            className="block w-full max-w-sm cursor-pointer rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-700 file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:text-slate-800 hover:file:bg-slate-200"
          />
          <span className="text-xs text-slate-500">
            code, configs, IaC and logs · max {MAX_CHARS.toLocaleString()} characters
          </span>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label htmlFor="material-text" className="text-sm font-medium text-slate-700">
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
        <label htmlFor="material-name" className="text-sm font-medium text-slate-700">
          Filename (used as analysis context)
        </label>
        <input
          id="material-name"
          type="text"
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          disabled={submitting}
          className="w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 outline-none focus:border-sky-600"
        />
      </div>

      <div className="flex flex-col gap-2">
        {providers.length > 0 ? (
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="llm-provider" className="text-sm font-medium text-slate-700">
                LLM provider
              </label>
              <select
                id="llm-provider"
                value={llmProvider}
                onChange={(event) => {
                  setLlmProvider(event.target.value);
                  writeLlmChoice({ provider: event.target.value });
                }}
                disabled={submitting}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-sky-600"
              >
                <option value="">
                  {requiresUserKey ? "No key — built-in rules only" : "Server default"}
                </option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="llm-model" className="text-sm font-medium text-slate-700">
                Model (optional)
              </label>
              <input
                id="llm-model"
                type="text"
                value={llmModel}
                onChange={(event) => {
                  const value = event.target.value.trim();
                  setLlmModel(value);
                  writeLlmChoice({ model: value });
                }}
                disabled={submitting}
                placeholder={
                  providers.find((p) => p.id === llmProvider)?.default_model ?? "provider default"
                }
                className="w-64 rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 outline-none focus:border-sky-600"
              />
            </div>
          </div>
        ) : null}
        <label htmlFor="llm-key" className="text-sm font-medium text-slate-700">
          Your LLM API key
        </label>
        <LlmKeyField
          id="llm-key"
          value={llmKey}
          disabled={submitting}
          onChange={(value) => {
            setLlmKey(value);
            writeLlmChoice({ key: value });
          }}
        />
        <p className="text-xs text-slate-500">
          Sent over HTTPS to this Vishap server, which forwards it only to the provider you
          picked, for your analysis. It is kept in this browser only and is not shown again.
        </p>
        {rulesOnly ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            No key entered: Vishap will run its built-in rule engine only (no LLM) — fast, free,
            and it catches injection, secrets, unsafe deserialization and more. Pick a provider
            and add your key for the full six-stage LLM analysis.
          </p>
        ) : null}
      </div>

      {error ? (
        <p className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
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
          {submitting ? "Submitting…" : rulesOnly ? "Analyze (no LLM)" : "Analyze"}
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
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
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
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 transition-colors hover:border-sky-600 hover:text-sky-700 disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          Load example
        </button>
      </div>
    </form>
  );
}

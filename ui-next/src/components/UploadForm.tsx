"use client";

import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { ChevronDown, FileUp, LoaderCircle, Sparkles, TriangleAlert } from "lucide-react";
import { rememberJob, submitAnalysis, getProviders, type LlmProvider } from "@/lib/api";
import { LLM_CHANGED, readLlmChoice, writeLlmChoice } from "@/lib/llmChoice";
import LlmKeyField from "@/components/LlmKeyField";
import { EXAMPLES, findExample } from "@/lib/examples";

const ACCEPTED_EXTENSIONS = [
  ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".h", ".cpp", ".go", ".php",
  ".tf", ".yaml", ".yml", ".json", ".sql", ".sh", ".log", ".txt", ".md",
];
const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");
/** The API rejects anything over 200,000 characters (HTTP 422), so stop it here. */
const MAX_CHARS = 200_000;

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
  // Browser-only values start empty (same markup as the server render) and are filled in
  // after mount; reading storage during the first render caused hydration error #418.
  const [llmKey, setLlmKey] = useState<string>("");
  const [providers, setProviders] = useState<LlmProvider[]>([]);
  const [llmProvider, setLlmProvider] = useState<string>("");
  const [llmModel, setLlmModel] = useState<string>("");
  const [requiresUserKey, setRequiresUserKey] = useState(false);
  // Only the server's built-in Claude key is used: no provider / model / key fields.
  const [serverKeyOnly, setServerKeyOnly] = useState(false);
  const [advancedChoice, setAdvancedChoice] = useState<boolean | null>(null);
  // A local model (Ollama) needs no key; the placeholder only satisfies the "has a key" checks.
  const keyless = providers.find((p) => p.id === llmProvider)?.needs_key === false;
  const effectiveKey = keyless ? "local" : llmKey;
  const rulesOnly = !serverKeyOnly && requiresUserKey && !effectiveKey; // no key entered on a public demo
  // Advanced stays folded until the visitor opens it, except when a key or provider was saved earlier.
  const advancedOpen = advancedChoice ?? Boolean(llmKey || llmProvider);
  // "Advanced" (own provider / key) stays folded until the visitor has used it.
  const [exampleId, setExampleId] = useState<string | null>(null);
  // "Analysis without LLM": the built-in rule engine only, no model and no key.
  const [noLlm, setNoLlm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getProviders()
      .then((list) => {
        if (cancelled) return;
        setProviders(list.providers);
        setRequiresUserKey(list.requiresUserKey);
        setServerKeyOnly(list.serverKeyOnly);
      })
      .catch(() => {
        /* older server without /providers: the server default is used */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // "Try with an example" links here with ?example=<id>: prefill the form once.
  // (Read from the URL after mount: the server render cannot know it.)
  useEffect(() => {
    function prefillFromUrl() {
      const example = findExample(new URLSearchParams(window.location.search).get("example"));
      if (!example) return;
      setMaterial((current) => current || example.material);
      setFilename((current) => (current === "pasted.txt" ? example.filename : current));
      setExampleId((current) => current ?? example.id);
    }
    prefillFromUrl();
  }, []);

  function loadExample(id: string) {
    const example = findExample(id);
    if (!example) return;
    setMaterial(example.material);
    setFilename(example.filename);
    setExampleId(example.id);
    setError(null);
  }

  // The settings panel edits the same browser-side choice; stay in sync with it.
  useEffect(() => {
    function sync() {
      const choice = readLlmChoice();
      setLlmKey(choice.key);
      setLlmProvider(choice.provider);
      setLlmModel(choice.model);
    }
    sync();
    window.addEventListener(LLM_CHANGED, sync);
    return () => window.removeEventListener(LLM_CHANGED, sync);
  }, []);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    setError(null);

    // generous byte pre-check (UTF-8 can be 4 bytes/char); the exact limit is in characters
    if (file.size > MAX_CHARS * 4) {
      setError(`File is too large. Limit: ${MAX_CHARS.toLocaleString("en-US")} characters.`);
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
          `File has ${text.length.toLocaleString("en-US")} characters; the limit is ${MAX_CHARS.toLocaleString("en-US")}. Split it into smaller parts.`,
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
        `Material has ${material.length.toLocaleString("en-US")} characters; the limit is ${MAX_CHARS.toLocaleString("en-US")}.`,
      );
      return;
    }
    if (!noLlm && !serverKeyOnly && llmProvider && !effectiveKey) {
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
        noLlm || serverKeyOnly ? undefined : effectiveKey || undefined,
        noLlm ? "rules" : !serverKeyOnly && effectiveKey ? llmProvider || undefined : undefined,
        noLlm || serverKeyOnly || !effectiveKey ? undefined : llmModel || undefined,
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
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-slate-700">Start with an example</legend>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example.id}
              type="button"
              onClick={() => loadExample(example.id)}
              disabled={submitting}
              aria-pressed={exampleId === example.id}
              title={example.blurb}
              className={`inline-flex min-h-11 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors disabled:opacity-50 sm:min-h-9 ${
                exampleId === example.id
                  ? "border-sky-600 bg-sky-50 text-sky-800"
                  : "border-slate-300 text-slate-800 hover:border-sky-600 hover:text-sky-700"
              }`}
            >
              <Sparkles className="h-4 w-4" aria-hidden="true" />
              {example.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-slate-600">
          Loads a small sample into the form. No key and no file needed.
        </p>
      </fieldset>

      <div className="flex flex-col gap-2">
        <label htmlFor="material-file" className="text-sm font-medium text-slate-700">
          Upload a file
        </label>
        <input
          id="material-file"
          ref={fileInputRef}
          type="file"
          accept={ACCEPT_ATTR}
          onChange={handleFileChange}
          disabled={submitting}
          title="Pick a code, config, IaC or log file from your computer"
          className="block w-full max-w-md cursor-pointer rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-700 file:mr-3 file:cursor-pointer file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:text-slate-800 hover:file:bg-slate-200"
        />
        <span className="text-xs text-slate-600">
          code, configs, IaC, specs and logs · max {MAX_CHARS.toLocaleString("en-US")} characters
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor="material-text" className="text-sm font-medium text-slate-700">
            …or paste the material
          </label>
          <span className="font-mono text-xs text-slate-600">
            {material.length.toLocaleString("en-US")} chars
          </span>
        </div>
        <textarea
          id="material-text"
          value={material}
          onChange={(event) => {
            setMaterial(event.target.value);
            setExampleId(null);
          }}
          disabled={submitting}
          spellCheck={false}
          placeholder="Paste code, config, spec, logs or data here…"
          title="The text Vishap will analyse"
          className="terminal min-h-64 w-full resize-y outline-none focus:border-sky-600 sm:min-h-72"
        />
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="material-name" className="text-sm font-medium text-slate-700">
          Filename
        </label>
        <input
          id="material-name"
          type="text"
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          disabled={submitting}
          title="The extension tells Vishap what kind of material this is (.py, .tf, .log, .yaml)"
          className="min-h-11 w-full max-w-sm rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 outline-none focus:border-sky-600 sm:min-h-10"
        />
        <span className="text-xs text-slate-600">
          Used as context: the extension (.py, .tf, .log, .yaml) selects the right checks.
        </span>
      </div>

      <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 px-4 py-3 text-sm">
        <input
          type="checkbox"
          checked={noLlm}
          onChange={(event) => setNoLlm(event.target.checked)}
          disabled={submitting}
          className="mt-0.5 h-5 w-5 shrink-0 accent-sky-600"
        />
        <span>
          <span className="block font-medium text-slate-800">Analysis without LLM</span>
          <span className="block text-xs text-slate-600">
            Built-in rules only: no model, no key, instant and free. It catches injection, hard-coded
            secrets, unsafe deserialization and more, but does not run the six-stage LLM analysis.
          </span>
        </span>
      </label>

      {noLlm ? null : serverKeyOnly ? (
        <p className="text-xs text-slate-600">
          Analysis runs on this server&apos;s built-in model. No API key is needed.
        </p>
      ) : (
        <>
          <details
            open={advancedOpen}
            onToggle={(event) => setAdvancedChoice(event.currentTarget.open)}
            className="group rounded-lg border border-slate-200 px-4 py-3"
          >
            <summary className="flex min-h-9 cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-slate-800 [&::-webkit-details-marker]:hidden">
              Advanced: use your own LLM provider and key
              <ChevronDown
                className="h-4 w-4 shrink-0 text-slate-500 transition-transform group-open:rotate-180"
                aria-hidden="true"
              />
            </summary>
            <div className="mt-3 flex flex-col gap-2">
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
                      className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-sky-600 sm:min-h-10"
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
                      className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 outline-none focus:border-sky-600 sm:min-h-10 sm:w-64"
                    />
                  </div>
                </div>
              ) : null}
              {keyless ? (
                <p className="text-xs text-slate-600">
                  Local model: no API key needed. It works when this Vishap server can reach your
                  model (for example Ollama on the same machine). Your material is not sent to a cloud
                  provider.
                </p>
              ) : (
                <>
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
                  <p className="text-xs text-slate-600">
                    Sent over HTTPS to this Vishap server, which forwards it only to the provider you
                    picked, for your analysis. It is kept in this browser only and is not shown again.
                  </p>
                </>
              )}
            </div>
          </details>
          {rulesOnly && !noLlm ? (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              No key entered: Vishap will run its built-in rule engine only (no LLM) — fast, free,
              and it catches injection, secrets, unsafe deserialization and more. Open Advanced and
              add a key for the full six-stage LLM analysis.
            </p>
          ) : null}
        </>
      )}

      {error ? (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          type="submit"
          disabled={submitting || !material.trim()}
          className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-sky-500 px-6 py-2 text-base font-semibold text-slate-950 transition-colors hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-300 sm:min-h-10 sm:w-auto sm:text-sm"
        >
          {submitting ? (
            <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <FileUp className="h-4 w-4" aria-hidden="true" />
          )}
          {submitting ? "Submitting…" : noLlm || (rulesOnly && !serverKeyOnly) ? "Analyze (no LLM)" : "Analyze"}
        </button>
        <button
          type="button"
          onClick={() => {
            setMaterial("");
            setFilename("pasted.txt");
            setError(null);
            setExampleId(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
          disabled={submitting}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900 disabled:opacity-50 sm:min-h-10 sm:w-auto"
        >
          Clear
        </button>
      </div>
    </form>
  );
}

import type {AnalyzeResponse, Job, Report} from "./types";
import { IS_DESKTOP } from "./desktop";

/** Base URL of the FastAPI backend. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:5001").replace(
  /\/+$/,
  "",
);

/** Optional key — the backend only enforces it when VISHAP_API_KEY is set. */
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? "";

type TauriInvoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

declare global {
  interface Window {
    // Injected by Tauri because `withGlobalTauri: true`; used only as a desktop
    // fallback when the webview's own fetch is blocked.
    __TAURI__?: { core?: { invoke?: TauriInvoke } };
  }
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailFrom(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  }
  return fallback;
}

/** Desktop fallback: perform the request in Rust over IPC.
 *
 * The webview's own `fetch` can be blocked by browser-level networking rules
 * (Private Network Access, a proxy, an AV shim) even though the shell's HTTP
 * works. `api_request` runs the same loopback request in Rust and returns the raw
 * status + body, so the UI still talks to the backend without the browser's
 * network stack. Only the desktop build has `window.__TAURI__`.
 */
async function apiViaTauri<T>(path: string, options: RequestInit): Promise<T> {
  const reply = (await window.__TAURI__!.core!.invoke!("api_request", {
    method: options.method ?? "GET",
    path,
    body: typeof options.body === "string" ? options.body : null,
    apiKey: API_KEY || null})) as { status: number; body: string };

  let body: unknown = null;
  if (reply.body) {
    try {
      body = JSON.parse(reply.body);
    } catch {
      body = reply.body;
    }
  }

  if (reply.status < 200 || reply.status >= 300) {
    throw new ApiError(
      detailFrom(body, `Request failed with HTTP ${reply.status}`),
      reply.status,
    );
  }

  return body as T;
}

/** Thin fetch wrapper: JSON in/out, `X-API-Key`, readable errors. */
export async function apiFetch<T>(
  path: string,
  options: RequestInit & { llmApiKey?: string; llmProvider?: string; llmModel?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }
  const llmApiKey = options.llmApiKey;
  if (llmApiKey) {
    headers.set("X-LLM-Api-Key", llmApiKey);
    // provider/model only make sense together with the caller's own key
    if (options.llmProvider) headers.set("X-LLM-Provider", options.llmProvider);
    if (options.llmModel) headers.set("X-LLM-Model", options.llmModel);
  }

  const canUseTauri =
    IS_DESKTOP && typeof window !== "undefined" && Boolean(window.__TAURI__?.core?.invoke);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers, cache: "no-store" });
  } catch {
    // On the desktop shell, fall back to the Rust IPC bridge before giving up.
    if (canUseTauri) {
      return await apiViaTauri<T>(path, options);
    }
    throw new ApiError(`Cannot reach the Vishap API at ${API_URL}. Is the backend running?`, 0);
  }

  // WebView2 can surface a CORS/PNA block as a `Response` with `status: 0` (or an
  // opaque response) instead of throwing — treat that exactly like a network
  // failure and route it through the IPC bridge too.
  if (response.status === 0 || response.type === "opaque") {
    if (canUseTauri) {
      return await apiViaTauri<T>(path, options);
    }
    throw new ApiError(`Cannot reach the Vishap API at ${API_URL}. Is the backend running?`, 0);
  }

  const raw = await response.text();
  let body: unknown = null;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }
  }

  if (!response.ok) {
    throw new ApiError(
      detailFrom(body, `Request failed with HTTP ${response.status}`),
      response.status,
    );
  }

  return body as T;
}

export interface LlmProvider {
  id: string;
  label: string;
  default_model: string;
}

/** Providers the server allows for bring-your-own-key requests. */
export async function getProviders(): Promise<LlmProvider[]> {
  const data = await apiFetch<{ providers: LlmProvider[] }>("/providers");
  return data.providers;
}

export function submitAnalysis(
  material: string,
  filename: string,
  llmApiKey?: string,
  llmProvider?: string,
  llmModel?: string,
): Promise<AnalyzeResponse> {
  return apiFetch<AnalyzeResponse>("/analyze/async", {
    method: "POST",
    llmApiKey,
    llmProvider,
    llmModel,
    body: JSON.stringify({ material, filename }),
  });
}

export function getJob(jobId: string): Promise<Job> {
  return apiFetch<Job>(`/status/${encodeURIComponent(jobId)}`);
}

export function getReport(jobId: string): Promise<Report> {
  return apiFetch<Report>(`/report/${encodeURIComponent(jobId)}`);
}

/** Forget a job; `/status` and `/report` answer 404 afterwards. */
export function deleteJob(jobId: string): Promise<{ deleted: boolean; job_id: string }> {
  return apiFetch<{ deleted: boolean; job_id: string }>(
    `/status/${encodeURIComponent(jobId)}`,
    { method: "DELETE" },
  );
}

/** Drop the server-side analysis history (the audit trail is separate). */
export function clearHistory(): Promise<{ status: string; removed: number }> {
  return apiFetch<{ status: string; removed: number }>("/history/clear", { method: "POST" });
}

/**
 * Fetch the audit trail as a file and hand it to the browser.
 *
 * Goes through `apiFetch` rather than a plain link so the `X-API-Key` header is
 * attached (a bare `<a href>` would be rejected once an API key is configured).
 */
export async function downloadAudit(format: "csv" | "json" = "json"): Promise<void> {
  const response = await fetch(`${API_URL}/audit/export?format=${format}`, {
    headers: API_KEY ? { "X-API-Key": API_KEY } : undefined,
    cache: "no-store"});
  if (!response.ok) {
    throw new ApiError(`Audit export failed with HTTP ${response.status}`, response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `vishap-audit.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/* -------------------------------------------------------------------------- *
 * Local job cache
 *
 * The backend has no "list jobs" endpoint (`/status/list` does not exist), so
 * the dashboard remembers the jobs this browser submitted and refreshes each
 * one through `GET /status/{id}`.
 * -------------------------------------------------------------------------- */

const STORAGE_KEY = "vishap.jobs.v1";
const MAX_REMEMBERED = 50;

export function listLocalJobs(): Job[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Job[]) : [];
  } catch {
    return [];
  }
}

export function saveLocalJobs(jobs: Job[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs.slice(0, MAX_REMEMBERED)));
  } catch {
    /* storage full or disabled — the dashboard still works, it just forgets */
  }
}

export function rememberJob(job: Job): void {
  const others = listLocalJobs().filter((item) => item.job_id !== job.job_id);
  saveLocalJobs([job, ...others]);
}

export function forgetJob(jobId: string): void {
  saveLocalJobs(listLocalJobs().filter((item) => item.job_id !== jobId));
}





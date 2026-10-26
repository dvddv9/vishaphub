/**
 * Shared API contracts.
 *
 * These mirror the FastAPI responses in `src/main.py` — keep them in sync:
 *   POST /analyze/async  -> AnalyzeResponse
 *   GET  /status/{id}    -> Job      (never carries the report itself)
 *   GET  /report/{id}    -> Report   (409 until the job is done)
 */

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  job_id: string;
  status: JobStatus;
  filename: string;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
}

export interface AnalyzeResponse {
  job_id: string;
  status: JobStatus;
}

/** The slice of the audit trail the UI surfaces. */
export interface AuditSummary {
  critique_verdict?: string;
  risk_verdict?: string;
  cwe_ids?: string[];
  owasp_categories?: string[];
  // v7.2
  fidelity_index?: number | null;
  fidelity_index_note?: string | null;
  bias_check?: { bias_check: string; flags?: string[] } | null;
  reproducer?: string | null;
  reproducer_verified?: boolean | null;
  reproducer_note?: string | null;
  negative_evidence?: Array<{ cwe: string; reason: string }> | null;
  report_date?: string | null;
  valid_until?: string | null;
  [key: string]: unknown;
}

/** `GET /report/{id}` returns the flat pipeline result, not a `{ result: ... }` wrapper. */
export interface Report {
  session_id: string;
  timestamp: string;
  filename: string;
  final_markdown: string;
  critique_verdict?: string;
  material_size?: number;
  cost_usd?: number;
  /** "static" = built-in rules only (no LLM key was supplied); "llm" = full pipeline. */
  mode?: "static" | "llm";
  audit?: AuditSummary;
  [key: string]: unknown;
}

export const TERMINAL_STATUSES: readonly JobStatus[] = ["done", "failed"];

export function isTerminal(status: JobStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}


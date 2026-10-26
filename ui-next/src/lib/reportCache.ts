import type { Report } from "./types";

/**
 * The hosted backend keeps jobs in memory, so a restart (deploy, free-tier sleep)
 * makes `/report/{id}` answer 404 for reports you already had. Keep a trimmed copy
 * of each finished report in this browser so "View" keeps working.
 */
const PREFIX = "vishap.report.";
const INDEX = "vishap.report.index";
const MAX_REPORTS = 20;

function readIndex(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(INDEX) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function cacheReport(jobId: string, report: Report): void {
  try {
    const audit = (report.audit ?? {}) as Record<string, unknown>;
    // keep what the page shows; drop the heavy per-stage payloads
    const slim = {
      session_id: report.session_id,
      timestamp: report.timestamp,
      filename: report.filename,
      final_markdown: report.final_markdown,
      cost_usd: report.cost_usd,
      mode: report.mode,
      audit: {
        risk_verdict: audit.risk_verdict,
        critique_verdict: audit.critique_verdict,
        cwe_ids: audit.cwe_ids,
        owasp_categories: audit.owasp_categories,
        fidelity_index: audit.fidelity_index,
        fidelity_index_note: audit.fidelity_index_note,
        bias_check: audit.bias_check,
        reproducer_verified: audit.reproducer_verified,
        reproducer_note: audit.reproducer_note,
        negative_evidence: audit.negative_evidence,
        report_date: audit.report_date,
        valid_until: audit.valid_until,
      },
    };
    localStorage.setItem(PREFIX + jobId, JSON.stringify(slim));
    const index = [jobId, ...readIndex().filter((id) => id !== jobId)];
    for (const old of index.slice(MAX_REPORTS)) localStorage.removeItem(PREFIX + old);
    localStorage.setItem(INDEX, JSON.stringify(index.slice(0, MAX_REPORTS)));
  } catch {
    /* storage full or blocked: the live report still works */
  }
}

export function readCachedReport(jobId: string): Report | null {
  try {
    const raw = localStorage.getItem(PREFIX + jobId);
    if (!raw) return null;
    return { ...(JSON.parse(raw) as Report), __fromBrowserCache: true };
  } catch {
    return null;
  }
}

export function dropCachedReport(jobId: string): void {
  try {
    localStorage.removeItem(PREFIX + jobId);
    localStorage.setItem(INDEX, JSON.stringify(readIndex().filter((id) => id !== jobId)));
  } catch {
    /* nothing to do */
  }
}

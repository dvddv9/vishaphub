"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  Check,
  Copy,
  Download,
  FileJson,
  LoaderCircle,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { ApiError, deleteJob, downloadAudit, forgetJob, getReport } from "@/lib/api";
import type { Report } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/time";
import { cacheReport, readCachedReport } from "@/lib/reportCache";

const BUTTON =
  "inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-800 transition-colors hover:border-sky-500 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-50";
const DANGER =
  "inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm text-red-700 transition-colors hover:border-red-300 hover:text-red-800 disabled:cursor-not-allowed disabled:opacity-50";

function ReportInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const jobId = searchParams.get("id") || "";

  const { data: report, error } = useSWR<Report>(
    jobId ? ["report", jobId] : null,
    async () => {
      try {
        const fresh = await getReport(jobId);
        cacheReport(jobId, fresh);
        return fresh;
      } catch (cause) {
        // The server forgot the job (restart), but this browser kept a copy of the report.
        if (cause instanceof ApiError && cause.status === 404) {
          const saved = readCachedReport(jobId);
          if (saved) return saved;
        }
        throw cause;
      }
    },
    {
      // `GET /report/{id}` answers 409 until the job is done — keep retrying.
      refreshInterval: (latest) => (latest ? 0 : 3000),
      // 409 = still running (keep polling); 404 = gone (stop, it will not come back)
      shouldRetryOnError: (cause: unknown) => !(cause instanceof ApiError && cause.status === 404),
      errorRetryInterval: 3000,
      revalidateOnFocus: false,
    },
  );

  const [copied, setCopied] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [auditBusy, setAuditBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const isStillRunning = error instanceof ApiError && error.status === 409;
  const isMissing = error instanceof ApiError && error.status === 404;

  function handleExport() {
    if (!report) return;
    const blob = new Blob([report.final_markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${report.filename.replace(/\.[^.]+$/, "") || "report"}-vishap.md`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function handleCopy() {
    if (!report) return;
    setActionError(null);
    try {
      await navigator.clipboard.writeText(report.final_markdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setActionError("Could not copy — the clipboard is blocked in this window.");
    }
  }

  async function handleAudit() {
    setActionError(null);
    setAuditBusy(true);
    try {
      await downloadAudit("json");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Audit export failed.");
    } finally {
      setAuditBusy(false);
    }
  }

  async function handleDelete() {
    if (!jobId) return;
    if (!window.confirm("Delete this job? The report file on disk is kept.")) return;
    setActionError(null);
    setDeleting(true);
    try {
      await deleteJob(jobId);
      forgetJob(jobId);
      router.push("/");
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Could not delete the job.");
      setDeleting(false);
    }
  }


  // v7.2: audit metadata
  const audit = report?.audit as
    | (Record<string, unknown> & {
        fidelity_index?: number | null;
        fidelity_index_note?: string | null;
        bias_check?: { bias_check: string; flags?: string[] } | null;
        reproducer_verified?: boolean | null;
        reproducer_note?: string | null;
        negative_evidence?: Array<{ cwe: string; reason: string }> | null;
        report_date?: string | null;
        valid_until?: string | null;
      })
    | undefined;

  const verdict = report?.audit?.risk_verdict ?? report?.critique_verdict ?? null;
  const rulesOnly = report?.mode === "static";

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-slate-600 transition-colors hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to dashboard
        </Link>

        <div className="flex flex-wrap items-center gap-2">
          {report ? (
            <>
              <button type="button" onClick={handleCopy} className={BUTTON}>
                {copied ? (
                  <Check className="h-4 w-4 text-emerald-600" aria-hidden="true" />
                ) : (
                  <Copy className="h-4 w-4" aria-hidden="true" />
                )}
                {copied ? "Copied" : "Copy"}
              </button>
              <button type="button" onClick={handleExport} className={BUTTON}>
                <Download className="h-4 w-4" aria-hidden="true" />
                Export .md
              </button>
            </>
          ) : null}

          <button
            type="button"
            onClick={handleAudit}
            disabled={auditBusy}
            title="Download the audit trail (JSON)"
            className={BUTTON}
          >
            {auditBusy ? (
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileJson className="h-4 w-4" aria-hidden="true" />
            )}
            Audit
          </button>

          {jobId ? (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting}
              title="Delete this job"
              className={DANGER}
            >
              {deleting ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              )}
              Delete
            </button>
          ) : null}
        </div>
      </div>

      {actionError ? (
        <p className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{actionError}</span>
        </p>
      ) : null}

      {report ? (
        <header className="mb-6">
          <h1 className="truncate font-mono text-xl text-slate-900" title={report.filename}>
            {report.filename}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="font-mono">{report.session_id}</span>
            {verdict ? (
              <span className="badge badge-running" title="Risk verdict">
                {verdict}
              </span>
            ) : null}
            {typeof report.cost_usd === "number" ? (
              <span>${report.cost_usd.toFixed(4)}</span>
            ) : null}
          </div>
        </header>
      ) : null}

      {report && report.__fromBrowserCache ? (
        <p className="mb-6 flex items-start gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Saved copy from this browser — the server no longer has this job (it restarted).
          </span>
        </p>
      ) : null}

      {report && rulesOnly ? (
        <p className="mb-6 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            Built-in rules only — no LLM was used. Findings below are pattern-based.{" "}
            <Link href="/analyze" className="font-medium underline">
              Run again with your own key
            </Link>{" "}
            for the full six-stage analysis.
          </span>
        </p>
      ) : null}

      {/* v7.2 audit metadata */}
      {/* these cards are computed from the LLM stages; a rules-only report has none */}
      {report && audit && !rulesOnly ? (
        <section className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Fidelity</div>
            <div className="text-lg font-mono text-slate-900">
              {audit.fidelity_index != null ? audit.fidelity_index.toFixed(2) : "n/a"}
            </div>
            {audit.fidelity_index_note ? (
              <div className="text-xs text-slate-500">{audit.fidelity_index_note}</div>
            ) : null}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Bias check</div>
            <div className="text-sm font-mono text-slate-900">
              {audit.bias_check?.bias_check ?? "n/a"}
            </div>
            {audit.bias_check?.flags && audit.bias_check.flags.length > 0 ? (
              <div className="text-xs text-amber-700">{audit.bias_check.flags.join(", ")}</div>
            ) : null}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Reproducer</div>
            <div className="text-sm font-mono text-slate-900">
              {audit.reproducer_verified ? "verified" : "not verified"}
            </div>
            {audit.reproducer_note ? (
              <div className="text-xs text-slate-500">{audit.reproducer_note}</div>
            ) : null}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3 sm:col-span-2">
            <div className="text-xs uppercase tracking-wide text-slate-500">Negative evidence</div>
            <div className="text-xs text-slate-700">
              {audit.negative_evidence && audit.negative_evidence.length > 0
                ? `${audit.negative_evidence.length} checked-but-not-found CWEs`
                : "n/a"}
            </div>
            {audit.negative_evidence && audit.negative_evidence.length > 0 ? (
              <ul className="mt-1 list-disc pl-4 text-xs text-slate-600">
                {audit.negative_evidence.slice(0, 5).map((e) => (
                  <li key={e.cwe}>
                    <span className="font-mono">{e.cwe}</span> — {e.reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="text-xs uppercase tracking-wide text-slate-500">Report date</div>
            <div className="text-xs font-mono text-slate-900">
              {audit.report_date ? formatDateTime(audit.report_date) : "n/a"}
            </div>
            <div className="text-xs text-slate-500">
              valid until {audit.valid_until ? formatDate(audit.valid_until) : "n/a"}
            </div>
          </div>
        </section>
      ) : null}

      {!report && isStillRunning ? (
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-6 text-sm text-slate-600">
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          The analysis is still running — this page updates automatically.
        </div>
      ) : null}

      {!report && isMissing ? (
        <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          Job <span className="font-mono">{jobId}</span> was not found.
        </p>
      ) : null}

      {!report && error && !isStillRunning && !isMissing ? (
        <p className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{error instanceof Error ? error.message : "Could not load the report."}</span>
        </p>
      ) : null}

      {!report && !error ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading report…
        </div>
      ) : null}

      {report ? (
        <article className="rounded-xl border border-slate-200 bg-white p-6">
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.final_markdown}</ReactMarkdown>
          </div>
        </article>
      ) : null}
    </div>
  );
}


export default function ReportPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading report...</div>}>
      <ReportInner />
    </Suspense>
  );
}

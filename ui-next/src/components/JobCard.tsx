"use client";

import { useState } from "react";
import Link from "next/link";
import { CircleCheckBig, CircleX, Clock, LoaderCircle, Trash2, TriangleAlert } from "lucide-react";
import type { Job, JobStatus } from "@/lib/types";

const STATUS_META: Record<
  JobStatus,
  { label: string; emoji: string; badge: string; icon: typeof Clock }
> = {
  queued: { label: "Queued", emoji: "🟡", badge: "badge badge-queued", icon: Clock },
  running: { label: "Running", emoji: "🔵", badge: "badge badge-running", icon: LoaderCircle },
  done: { label: "Done", emoji: "🟢", badge: "badge badge-done", icon: CircleCheckBig },
  failed: { label: "Failed", emoji: "🔴", badge: "badge badge-failed", icon: CircleX },
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export default function JobCard({
  job,
  onDelete,
}: {
  job: Job;
  /** Called after the job was deleted on the server, so the list can refresh. */
  onDelete?: (jobId: string) => void | Promise<void>;
}) {
  const meta = STATUS_META[job.status] ?? STATUS_META.queued;
  const Icon = meta.icon;
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    if (!onDelete) return;
    if (!window.confirm(`Delete ${job.filename}? The report file on disk is kept.`)) return;
    setError(null);
    setDeleting(true);
    try {
      await onDelete(job.job_id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete the job.");
      setDeleting(false);
    }
  }

  return (
    <article className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-slate-300 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={meta.badge}>
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {meta.label}
          </span>
          <h3 className="truncate font-mono text-sm text-slate-800" title={job.filename}>
            {job.filename}
          </h3>
        </div>
        <p className="mt-1.5 text-xs text-slate-500">
          Created {formatTimestamp(job.created_at)}
          {job.finished_at ? ` · finished ${formatTimestamp(job.finished_at)}` : ""}
        </p>
        {job.status === "failed" && job.error ? (
          <p className="mt-1.5 flex items-start gap-1.5 text-xs text-red-600">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="break-words">{job.error}</span>
          </p>
        ) : null}
        {error ? (
          <p className="mt-1.5 flex items-start gap-1.5 text-xs text-red-600">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="break-words">{error}</span>
          </p>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {job.status === "done" ? (
          <Link
            href={`/report?id=${encodeURIComponent(job.job_id)}`}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-800 transition-colors hover:border-sky-500 hover:text-sky-700"
          >
            View
          </Link>
        ) : (
          <Link
            href={`/report?id=${encodeURIComponent(job.job_id)}`}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-700"
          >
            Open
          </Link>
        )}
        {onDelete ? (
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleting}
            title="Delete this job"
            aria-label={`Delete ${job.filename}`}
            className="rounded-md border border-slate-200 p-1.5 text-slate-500 transition-colors hover:border-red-300 hover:text-red-300 disabled:opacity-50"
          >
            {deleting ? (
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        ) : null}
        <span className="hidden font-mono text-[0.7rem] text-slate-600 sm:inline">
          {job.job_id.slice(0, 8)}
        </span>
      </div>
    </article>
  );
}

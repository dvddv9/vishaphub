"use client";

import LLMSettings from "@/components/LLMSettings";

import Link from "next/link";
import useSWR from "swr";
import { useState } from "react";
import {
  FileJson,
  FileText,
  LoaderCircle,
  RefreshCw,
  Search,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import JobCard from "@/components/JobCard";
import Hero from "@/components/Hero";
import FeatureGrid from "@/components/FeatureGrid";
import EmptyState from "@/components/EmptyState";
import {
  clearHistory,
  deleteJob,
  downloadAudit,
  forgetJob,
  getJob,
  listLocalJobs,
  saveLocalJobs,
} from "@/lib/api";
import { IS_DESKTOP } from "@/lib/desktop";
import { isTerminal, type Job } from "@/lib/types";

/** What the page knows about the session. `local` = desktop build, always allowed. */
type AuthState = "loading" | "signed-in" | "signed-out" | "local";

/**
 * Refresh every remembered job that has not reached a terminal state.
 * There is no "list jobs" endpoint, so the browser keeps its own list.
 */
async function refreshJobs(): Promise<Job[]> {
  const stored = listLocalJobs();
  if (stored.length === 0) return stored;

  const refreshed = await Promise.all(
    stored.map(async (job) => {
      if (isTerminal(job.status)) return job;
      try {
        return await getJob(job.job_id);
      } catch {
        return job;
      }
    }),
  );

  if (JSON.stringify(refreshed) !== JSON.stringify(stored)) {
    saveLocalJobs(refreshed);
  }

  return refreshed;
}

function Dashboard({ auth }: { auth: AuthState }) {
  // The desktop build has no accounts: whoever runs the app may analyze.
  const canAnalyze = auth === "signed-in" || auth === "local";

  const { data: jobs, error, isLoading, mutate } = useSWR<Job[]>("vishap:jobs", refreshJobs, {
    revalidateOnFocus: true,
    refreshInterval: (latest) =>
      latest && latest.some((job) => !isTerminal(job.status)) ? 2000 : 0,
  });

  const [clearing, setClearing] = useState(false);
  const [auditBusy, setAuditBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function handleClearHistory() {
    if (!window.confirm("Clear the analysis history? Reports already written stay on disk.")) return;
    setActionError(null);
    setClearing(true);
    try {
      await clearHistory();
      saveLocalJobs([]);
      await mutate();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "Could not clear the history.");
    } finally {
      setClearing(false);
    }
  }

  async function handleDeleteJob(jobId: string) {
    await deleteJob(jobId);
    forgetJob(jobId);
    await mutate();
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

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10">
      <Hero canAnalyze={canAnalyze} />

      <FeatureGrid />

      {auth === "loading" ? (
        <div className="mt-8 flex items-center gap-2 text-sm text-slate-500">
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          Checking your session…
        </div>
      ) : canAnalyze ? (
        <section className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            href="/analyze"
            className="inline-flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-sky-400"
          >
            <Search className="h-4 w-4" aria-hidden="true" />
            New analysis
          </Link>
          <button
            type="button"
            onClick={() => void mutate()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 shadow-sm transition-colors hover:border-slate-400 hover:bg-slate-50"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
          <button
            type="button"
            onClick={handleAudit}
            disabled={auditBusy}
            title="Download the audit trail (JSON)"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 shadow-sm transition-colors hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50"
          >
            {auditBusy ? (
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <FileJson className="h-4 w-4" aria-hidden="true" />
            )}
            Audit
          </button>
          <button
            type="button"
            onClick={handleClearHistory}
            disabled={clearing || !jobs?.length}
            title="Clear the analysis history"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 shadow-sm transition-colors hover:border-red-300 hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {clearing ? (
              <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            )}
            Clear history
          </button>
        </section>
      ) : (
        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-medium text-slate-900">Sign in to run an analysis</h2>
          <p className="mt-1 max-w-xl text-sm text-slate-600">
            Analyses are tied to your account. Sign in with Clerk to upload material and read the
            generated report.
          </p>
        </section>
      )}

      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-medium text-slate-900">Recent analyses</h2>
          {isLoading ? (
            <span className="flex items-center gap-1.5 text-xs text-slate-500">
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Loading
            </span>
          ) : null}
        </div>

        {actionError ? (
          <p className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{actionError}</span>
          </p>
        ) : null}

        <div className="mt-4 flex flex-col gap-3">
          {error ? (
            <p className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error instanceof Error ? error.message : "Could not load jobs."}</span>
            </p>
          ) : null}

          {!error && jobs && jobs.length === 0 ? (
            <EmptyState />
          ) : null}

                    {jobs?.map((job) => (
            <JobCard key={job.job_id} job={job} onDelete={handleDeleteJob} />
          ))}
        </div>
      </section>

      <section className="mt-10" aria-label="LLM provider settings">
        <LLMSettings />
      </section>
    </div>
  );
}

/** Web build: the session comes from Clerk. */
function WebDashboard() {
  const { isLoaded, isSignedIn } = useUser();

  if (!isLoaded) return <Dashboard auth="loading" />;
  return <Dashboard auth="local" />;
}

export default function DashboardPage() {
  // Desktop build: ClerkProvider is not mounted, so its hooks must never run.
  if (IS_DESKTOP) return <Dashboard auth="local" />;

  return <WebDashboard />;
}

// Local stubs instead of Clerk (dev/desktop: no Clerk keys needed).
const SignInButton = ({ children }: { children?: React.ReactNode }) => <>{children}</>;
const useUser = () => ({ isLoaded: true, isSignedIn: false as const, user: null });

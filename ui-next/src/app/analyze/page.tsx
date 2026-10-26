"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import {
  ArrowLeft,
  CircleCheckBig,
  CircleX,
  Clock,
  LoaderCircle,
  TriangleAlert,
} from "lucide-react";
import UploadForm from "@/components/UploadForm";
import { getJob, rememberJob } from "@/lib/api";
import { isTerminal, type Job, type JobStatus } from "@/lib/types";

const STEPS: { status: JobStatus; label: string }[] = [
  { status: "queued", label: "Queued" },
  { status: "running", label: "Analysing" },
  { status: "done", label: "Report ready" },
];

function stepState(current: JobStatus, step: JobStatus): "done" | "active" | "pending" | "failed" {
  if (current === "failed") return "failed";
  const order = STEPS.map((entry) => entry.status);
  const currentIndex = order.indexOf(current);
  const stepIndex = order.indexOf(step);
  if (stepIndex < currentIndex) return "done";
  if (stepIndex === currentIndex) return "active";
  return "pending";
}

export default function AnalyzePage() {
  const router = useRouter();
  const [jobId, setJobId] = useState<string | null>(null);

  const { data: job, error } = useSWR<Job>(
    jobId ? ["job", jobId] : null,
    () => getJob(jobId as string),
    {
      refreshInterval: (latest) => (latest && isTerminal(latest.status) ? 0 : 2000),
      revalidateOnFocus: false,
    },
  );

  useEffect(() => {
    if (!job) return;
    rememberJob(job);
    if (job.status === "done") {
      router.push(`/report?id=${encodeURIComponent(job.job_id)}`);
    }
  }, [job, router]);

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10">
      <Link
        href="/"
        className="mb-6 inline-flex items-center gap-1.5 text-sm text-slate-600 transition-colors hover:text-slate-900"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Back to dashboard
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">New analysis</h1>
      <p className="mt-1 text-sm text-slate-600">
        Upload a file or paste material. Vishap runs the six-stage pipeline asynchronously and
        redirects you to the report when it is ready.
      </p>

      {!jobId ? (
        <section className="mt-8">
          <UploadForm onSubmitted={(id) => setJobId(id)} />
        </section>
      ) : (
        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-500">Job</p>
              <p className="font-mono text-sm text-slate-800">{jobId}</p>
            </div>
            <button
              type="button"
              onClick={() => setJobId(null)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition-colors hover:border-slate-400 hover:text-slate-900"
            >
              Start another
            </button>
          </div>

          <ol className="mt-6 flex flex-col gap-3">
            {STEPS.map((step) => {
              const state = job ? stepState(job.status, step.status) : "pending";
              return (
                <li key={step.status} className="flex items-center gap-3">
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full border ${
                      state === "done"
                        ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                        : state === "active"
                          ? "border-sky-300 bg-sky-50 text-sky-700"
                          : state === "failed"
                            ? "border-red-300 bg-red-50 text-red-600"
                            : "border-slate-300 text-slate-500"
                    }`}
                  >
                    {state === "done" ? (
                      <CircleCheckBig className="h-4 w-4" aria-hidden="true" />
                    ) : state === "active" ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
                    ) : state === "failed" ? (
                      <CircleX className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Clock className="h-4 w-4" aria-hidden="true" />
                    )}
                  </span>
                  <span
                    className={
                      state === "pending" ? "text-sm text-slate-500" : "text-sm text-slate-800"
                    }
                  >
                    {step.label}
                  </span>
                </li>
              );
            })}
          </ol>

          {job?.status === "failed" ? (
            <p className="mt-5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{job.error ?? "The pipeline failed."}</span>
            </p>
          ) : null}

          {error ? (
            <p className="mt-5 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error instanceof Error ? error.message : "Could not read the job status."}</span>
            </p>
          ) : null}
        </section>
      )}
    </div>
  );
}

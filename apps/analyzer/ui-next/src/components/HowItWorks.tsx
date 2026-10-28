import Link from "next/link";
import { ArrowRight } from "lucide-react";

const STEPS = [
  {
    n: "1",
    title: "Paste or upload",
    body: "Code, a config, an API spec, a log or plain data. Up to 200,000 characters.",
  },
  {
    n: "2",
    title: "Press Analyze",
    body: "Rules run first, then the six-stage LLM pipeline. A run takes about a minute.",
  },
  {
    n: "3",
    title: "Read the report",
    body: "A verdict on top, then risks, a runbook with fix steps and the audit trail.",
  },
];

/** Three steps, shown on the dashboard and above the analysis form. */
export default function HowItWorks({ withLink = false }: { withLink?: boolean }) {
  return (
    <section aria-labelledby="how-it-works" className="w-full pb-10">
      <h2 id="how-it-works" className="text-lg font-medium text-slate-900">
        How it works
      </h2>
      <ol className="mt-4 grid gap-3 sm:grid-cols-3">
        {STEPS.map((step) => (
          <li
            key={step.n}
            className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 font-mono text-sm font-semibold text-emerald-700"
            >
              {step.n}
            </span>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{step.title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">{step.body}</p>
            </div>
          </li>
        ))}
      </ol>
      {withLink ? (
        <Link
          href="/analyze?example=sqli"
          className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-sky-700 hover:underline"
        >
          Start with an example
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      ) : null}
    </section>
  );
}

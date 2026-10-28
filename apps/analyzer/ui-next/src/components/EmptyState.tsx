import Link from "next/link";
import { EXAMPLES } from "@/lib/examples";

export default function EmptyState() {
  return (
    <div className="mx-auto mt-4 max-w-2xl rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center shadow-sm sm:p-10">
      <h3 className="text-lg font-semibold text-slate-900">No analyses yet</h3>
      <p className="mt-2 text-sm text-slate-600">
        Pick an example to see a full report in about a minute. No key and no setup needed.
      </p>
      <ul className="mt-6 grid gap-3 text-left sm:grid-cols-2">
        {EXAMPLES.map((example) => (
          <li key={example.id}>
            <Link
              href={`/analyze?example=${example.id}`}
              className="flex h-full min-h-14 flex-col justify-center rounded-xl border border-slate-200 px-4 py-3 transition-colors hover:border-sky-500"
            >
              <span className="text-sm font-semibold text-slate-900">{example.label}</span>
              <span className="mt-0.5 text-xs text-slate-600">{example.blurb}</span>
            </Link>
          </li>
        ))}
      </ul>
      <Link
        href="/analyze"
        className="mt-5 inline-flex min-h-11 items-center rounded-lg border border-slate-300 px-5 text-sm font-medium text-slate-800 transition-colors hover:border-sky-500 hover:text-sky-700"
      >
        Analyze my own file
      </Link>
    </div>
  );
}

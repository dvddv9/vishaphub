import Link from "next/link";
import { Shield, Zap, FileJson, ArrowRight, Terminal } from "lucide-react";

const SAMPLE = [
  "$ vishap analyze handlers/query.py",
  "  stage 1  ingest        ok",
  "  stage 2  taint         ok",
  "  stage 3  dataflow      ok",
  "  stage 4  risk          CRITICAL  CWE-89  line 42",
  "  stage 5  verdict       REQUIRES_REVIEW",
  "  stage 6  report        sarif 2.1.0 · sha256 ✓",
];

export default function Hero({ canAnalyze }: { canAnalyze: boolean }) {
  return (
    <section className="relative isolate overflow-hidden bg-slate-950 text-slate-100">
      {/* grid + glow */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.18]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgb(148 163 184 / 0.35) 1px, transparent 1px), linear-gradient(to bottom, rgb(148 163 184 / 0.35) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 0%, black 40%, transparent 100%)",
        }}
      />
      <div className="pointer-events-none absolute -top-32 left-1/2 h-[420px] w-[720px] -translate-x-1/2 rounded-full bg-emerald-500/20 blur-[120px]" />

      <div className="relative mx-auto grid w-full max-w-6xl gap-12 px-5 py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:py-28">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-emerald-300">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            deterministic SAST · six-stage LLM
          </p>

          <h1 className="mt-7 text-[2.75rem] font-semibold leading-[1.03] tracking-tight sm:text-6xl">
            Find the bug
            <br />
            <span className="text-emerald-400">before</span> it ships.
          </h1>

          <p className="mt-6 max-w-xl text-[15px] leading-relaxed text-slate-400">
            Code, specs, logs, IaC. Pattern rules catch injection before the model
            speaks, then six stages turn findings into a verdict, a STRIDE model and
            a SARIF report with SHA-256 provenance.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/analyze"
              className="group inline-flex items-center gap-2 rounded-lg bg-emerald-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-300"
            >
              {canAnalyze ? "Run an analysis" : "Analyse a file"}
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
            </Link>
            <Link
              href="/analyze?example=sqli"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-6 py-3 text-sm font-medium text-slate-300 transition-colors hover:border-slate-500 hover:text-white"
            >
              Load the SQLi example
            </Link>
            <span className="font-mono text-[11px] text-slate-500">30 free runs a day · no key needed</span>
          </div>

          <dl className="mt-12 grid gap-3 sm:grid-cols-3">
            <Stat icon={<Shield className="h-4 w-4" />} label="SAST / SCA" value="rules first" />
            <Stat icon={<Zap className="h-4 w-4" />} label="STRIDE" value="per finding" />
            <Stat icon={<FileJson className="h-4 w-4" />} label="SARIF" value="2.1.0 export" />
          </dl>
        </div>

        {/* terminal card */}
        <div className="relative">
          <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-emerald-500/10 to-sky-500/10 blur-2xl" />
          <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 shadow-2xl backdrop-blur">
            <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3">
              <Terminal className="h-3.5 w-3.5 text-slate-500" />
              <span className="font-mono text-[11px] text-slate-500">vishap · pipeline</span>
              <span className="ml-auto font-mono text-[10px] text-emerald-400">live</span>
            </div>
            <pre className="overflow-x-auto px-4 py-4 font-mono text-[12px] leading-6 text-slate-400">
              {SAMPLE.map((line) => {
                const critical = line.includes("CRITICAL");
                return (
                  <div key={line} className={critical ? "text-rose-400" : undefined}>
                    {line}
                  </div>
                );
              })}
            </pre>
            <div className="grid grid-cols-3 divide-x divide-slate-800 border-t border-slate-800 text-center">
              <Cell k="verdict" v="review" />
              <Cell k="findings" v="2" />
              <Cell k="audit" v="sha-256" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
      <dt className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-500">
        <span className="text-emerald-400">{icon}</span>
        {label}
      </dt>
      <dd className="mt-1 text-sm text-slate-200">{value}</dd>
    </div>
  );
}

function Cell({ k, v }: { k: string; v: string }) {
  return (
    <div className="px-2 py-3">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-600">{k}</div>
      <div className="mt-0.5 text-sm text-slate-300">{v}</div>
    </div>
  );
}

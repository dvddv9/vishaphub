import Link from "next/link";
import { Shield, Zap, FileJson, ArrowRight, FileText } from "lucide-react";

const REPO_URL = "https://github.com/dvddv9/vishap#readme";

export default function Hero({ canAnalyze }: { canAnalyze: boolean }) {
  return (
    // `palette-default` keeps this section dark in both themes (see theme-dark.css).
    <section className="palette-default relative isolate overflow-hidden rounded-2xl bg-slate-950 text-slate-100">
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
      <div className="pointer-events-none absolute -top-32 left-1/2 h-[420px] w-[720px] max-w-full -translate-x-1/2 rounded-full bg-emerald-500/20 blur-[120px]" />

      <div className="relative mx-auto grid w-full max-w-6xl gap-10 px-5 py-14 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-12 lg:py-24">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.12em] text-emerald-300">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            Multi-material IT analyst
          </p>

          <h1 className="mt-6 text-[2.5rem] font-semibold leading-[1.05] tracking-tight sm:text-6xl">
            Find the bug
            <br />
            <span className="text-emerald-400">before</span> it ships.
          </h1>

          <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-300">
            Paste code, a config, an API spec, a log or plain data. Rules catch the obvious first,
            then a six-stage LLM pipeline turns what they found into a verdict, a runbook with fix
            steps and an audit trail with SHA-256 provenance.
          </p>
          <p className="mt-3 font-mono text-xs text-slate-400">
            6-stage LLM pipeline · audit trail · SHA-256 · compliance
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/analyze?example=sqli"
              className="group inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-400 px-6 py-3 text-sm font-semibold text-slate-950 transition-colors hover:bg-emerald-300"
            >
              Try with an example
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
            </Link>
            <Link
              href="/analyze"
              className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-600 px-6 py-3 text-sm font-medium text-slate-100 transition-colors hover:border-slate-400 hover:text-white"
            >
              {canAnalyze ? "Analyze my own file" : "Analyse a file"}
            </Link>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center px-2 text-sm text-slate-300 underline-offset-4 hover:text-white hover:underline"
            >
              Install (pip / Docker)
            </a>
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Free demo, no key needed. A daily limit applies to each visitor and to the whole demo.
          </p>

          <dl className="mt-10 grid gap-3 sm:grid-cols-3">
            <Stat icon={<Shield className="h-4 w-4" />} label="SAST / SCA" value="rules first" />
            <Stat icon={<Zap className="h-4 w-4" />} label="STRIDE" value="per finding" />
            <Stat icon={<FileJson className="h-4 w-4" />} label="SARIF" value="2.1.0 export" />
          </dl>
        </div>

        {/* What you get: an illustrative report, not a live one */}
        <div className="relative">
          <div className="absolute -inset-4 rounded-3xl bg-gradient-to-br from-emerald-500/10 to-sky-500/10 blur-2xl" />
          <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 shadow-2xl backdrop-blur">
            <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3">
              <FileText className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
              <span className="font-mono text-[11px] text-slate-300">handlers/query.py</span>
              <span className="ml-auto font-mono text-[10px] text-slate-400">example report</span>
            </div>

            <div className="grid grid-cols-3 divide-x divide-slate-800 border-b border-slate-800 text-center">
              <Cell k="verdict" v="REQUIRES_REVIEW" accent />
              <Cell k="FI" v="0.82" />
              <Cell k="critical" v="1" />
            </div>

            <div className="space-y-4 px-4 py-4 text-sm">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">Risks</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-rose-400/40 bg-rose-400/10 px-2 py-0.5 font-mono text-[11px] text-rose-300">
                    critical
                  </span>
                  <span className="font-mono text-xs text-slate-200">CWE-89</span>
                  <span className="text-xs text-slate-300">query built from request data</span>
                </div>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">Runbook</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-relaxed text-slate-300">
                  <li>Block the endpoint (feature flag / WAF rule).</li>
                  <li>Replace string concatenation with parameterized queries.</li>
                </ul>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">Audit</p>
                <p className="mt-2 break-all font-mono text-xs text-slate-300">
                  sha256:9f2c…e1 · valid 90 days
                </p>
              </div>
            </div>
          </div>
          <p className="mt-3 text-center text-xs text-slate-400">Illustrative output, not a live result.</p>
        </div>
      </div>
    </section>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 px-4 py-3">
      <dt className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">
        <span className="text-emerald-400">{icon}</span>
        {label}
      </dt>
      <dd className="mt-1 text-sm text-slate-200">{value}</dd>
    </div>
  );
}

function Cell({ k, v, accent = false }: { k: string; v: string; accent?: boolean }) {
  return (
    <div className="px-2 py-3">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">{k}</div>
      <div className={`mt-0.5 break-words text-xs font-semibold sm:text-sm ${accent ? "text-amber-300" : "text-slate-100"}`}>
        {v}
      </div>
    </div>
  );
}

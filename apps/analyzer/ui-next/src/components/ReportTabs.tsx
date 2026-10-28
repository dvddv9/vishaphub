"use client";

import { useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, TriangleAlert } from "lucide-react";
import type { Report } from "@/lib/types";
import { formatDate, formatDateTime } from "@/lib/time";
import { useIsNarrow } from "@/lib/useMedia";
import {
  countLevels,
  extractSection,
  isStale,
  readRisks,
  readRunbook,
  trimTo,
  type Level,
  type RiskRow,
  type RunbookEntry,
} from "@/lib/reportView";

type TabId = "summary" | "risks" | "runbook" | "audit" | "raw";

const LEVEL_BADGE: Record<Level, string> = {
  critical: "badge badge-failed",
  high: "badge badge-queued",
  medium: "badge badge-running",
  low: "badge badge-done",
  unknown: "badge badge-neutral",
};

const LEVEL_LABEL: Record<Level, string> = {
  critical: "critical",
  high: "high",
  medium: "medium",
  low: "low",
  unknown: "n/a",
};

function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

function LevelBadge({ row }: { row: RiskRow }) {
  return (
    <span className={LEVEL_BADGE[row.level]} title={row.priority || undefined}>
      {LEVEL_LABEL[row.level]}
    </span>
  );
}

/* ----------------------------------------------------------------------------
 * Panels
 * -------------------------------------------------------------------------- */

function SummaryPanel({
  report,
  risks,
  runbook,
  stale,
  rulesOnly,
  onOpenFull,
}: {
  report: Report;
  risks: RiskRow[];
  runbook: RunbookEntry[];
  stale: boolean;
  rulesOnly: boolean;
  onOpenFull: () => void;
}) {
  const audit = report.audit;
  const verdict = audit?.risk_verdict ?? report.critique_verdict ?? null;
  const critique = audit?.critique_verdict ?? report.critique_verdict ?? null;
  const counts = countLevels(risks);
  const fidelity = audit?.fidelity_index;
  const conclusion = extractSection(report.final_markdown, "CONCLUSION");

  return (
    <div className="space-y-5">
      {stale ? (
        <p
          role="note"
          className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            This report is past its 90-day validity
            {audit?.valid_until ? ` (${formatDate(audit.valid_until)})` : ""}. New CVEs and advisories
            may have appeared since; run the analysis again before relying on it.
          </span>
        </p>
      ) : null}

      <dl className="divide-y divide-slate-200 rounded-xl border border-slate-200">
        <Row label="Verdict">
          <span className="inline-flex flex-wrap items-center gap-2">
            {verdict ? <span className="badge badge-running">{verdict}</span> : <span>n/a</span>}
            {critique && critique !== verdict ? (
              <span className="text-xs text-slate-600">critique: {critique}</span>
            ) : null}
            {stale ? <span className="badge badge-queued">stale</span> : null}
          </span>
        </Row>
        <Row label="Fidelity (FI)">
          <span className="font-mono">
            {typeof fidelity === "number" ? fidelity.toFixed(2) : "n/a"}
          </span>
          {rulesOnly ? <span className="ml-2 text-xs text-slate-600">rules only: not scored</span> : null}
        </Row>
        <Row label="Critical">
          <span className={counts.critical > 0 ? "font-semibold text-red-700" : undefined}>
            {counts.critical}
          </span>
        </Row>
        <Row label="Important (high + medium)">{counts.important}</Row>
        <Row label="Runbook">
          {runbook.length > 0
            ? `${runbook.length} ${runbook.length === 1 ? "weakness" : "weaknesses"} with steps`
            : "none for this report"}
        </Row>
      </dl>

      {conclusion ? (
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Conclusion</h3>
          <div className="mt-2 border-l-2 border-slate-300 pl-4">
            <Markdown>{trimTo(conclusion, 700)}</Markdown>
          </div>
        </div>
      ) : null}

      <button
        type="button"
        onClick={onOpenFull}
        className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 px-4 text-sm text-slate-800 transition-colors hover:border-sky-500 hover:text-sky-700 sm:min-h-9"
      >
        Read the full report
      </button>
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 px-4 py-3 text-sm sm:grid-cols-[14rem_1fr]">
      <dt className="text-slate-600">{label}</dt>
      <dd className="text-slate-900">{children}</dd>
    </div>
  );
}

function RisksPanel({ risks }: { risks: RiskRow[] }) {
  if (risks.length === 0) {
    return (
      <p className="text-sm text-slate-600">
        No structured findings in this report. The written report may still describe
        observations; open the Full report tab.
      </p>
    );
  }
  return (
    <>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full border-collapse text-left text-sm">
          <caption className="sr-only">Findings</caption>
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-600">
              <th scope="col" className="py-2 pr-3 font-medium">ID</th>
              <th scope="col" className="py-2 pr-3 font-medium">CWE</th>
              <th scope="col" className="py-2 pr-3 font-medium">Severity</th>
              <th scope="col" className="py-2 pr-3 font-medium">Axis</th>
              <th scope="col" className="py-2 pr-3 font-medium">Confidence</th>
              <th scope="col" className="py-2 font-medium">Note</th>
            </tr>
          </thead>
          <tbody>
            {risks.map((row) => (
              <tr key={`${row.id}-${row.cwe}`} className="border-b border-slate-200 align-top">
                <td className="py-2 pr-3 font-mono text-xs text-slate-800">{row.id}</td>
                <td className="py-2 pr-3 font-mono text-xs text-slate-800">{row.cwe || "n/a"}</td>
                <td className="py-2 pr-3"><LevelBadge row={row} /></td>
                <td className="py-2 pr-3 text-slate-700">{row.axis || "n/a"}</td>
                <td className="py-2 pr-3 font-mono text-xs text-slate-700">{row.confidence || "n/a"}</td>
                <td className="py-2 text-slate-700">{row.note || "n/a"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-3 sm:hidden">
        {risks.map((row) => (
          <li
            key={`${row.id}-${row.cwe}`}
            className="rounded-xl border border-slate-200 p-3 text-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-slate-800">{row.id}</span>
              {row.cwe ? <span className="font-mono text-xs text-slate-800">{row.cwe}</span> : null}
              <LevelBadge row={row} />
            </div>
            {row.note ? <p className="mt-2 text-slate-700">{row.note}</p> : null}
            {row.axis || row.confidence ? (
              <p className="mt-2 text-xs text-slate-600">
                {row.axis ? `axis: ${row.axis}` : ""}
                {row.axis && row.confidence ? " · " : ""}
                {row.confidence ? `confidence: ${row.confidence}` : ""}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}

function StepGroup({ title, steps }: { title: string; steps: string[] }) {
  if (steps.length === 0) return null;
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">{title}</h4>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-800">
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
    </div>
  );
}

function RunbookPanel({ runbook, fallbackMarkdown }: { runbook: RunbookEntry[]; fallbackMarkdown: string }) {
  if (runbook.length === 0) {
    return fallbackMarkdown ? (
      <Markdown>{fallbackMarkdown}</Markdown>
    ) : (
      <p className="text-sm text-slate-600">
        No runbook for this report: it is built from the weaknesses (CWE) the analysis found, and
        none of them has a prepared procedure.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      {runbook.map((entry) => (
        <article key={entry.cwe} className="rounded-xl border border-slate-200 p-4">
          <header className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-slate-800">{entry.cwe}</span>
            <h3 className="text-sm font-semibold text-slate-900">{entry.title || "Runbook"}</h3>
            {entry.severity ? <span className="badge badge-neutral">{entry.severity}</span> : null}
          </header>
          <div className="mt-3 space-y-3">
            <StepGroup title="Immediately" steps={entry.immediate} />
            <StepGroup title="Short term" steps={entry.shortTerm} />
            <StepGroup title="Long term" steps={entry.longTerm} />
            {entry.escalation ? (
              <p className="text-sm text-slate-700">
                <span className="font-semibold text-slate-900">Escalate to:</span> {entry.escalation}
              </p>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}

function Card({ title, children, wide = false }: { title: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`rounded-xl border border-slate-200 p-3 ${wide ? "sm:col-span-2" : ""}`}>
      <div className="text-xs uppercase tracking-wide text-slate-600">{title}</div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function AuditPanel({ report, stale, rulesOnly }: { report: Report; stale: boolean; rulesOnly: boolean }) {
  const audit = report.audit;
  const text = (value: unknown): string => (typeof value === "string" ? value : "");
  const hash = text(audit?.material_hash);
  const auditId = text(audit?.audit_id);
  const generator = text(audit?.generator);
  const evidence = audit?.negative_evidence ?? null;

  return (
    <div className="space-y-5">
      <dl className="divide-y divide-slate-200 rounded-xl border border-slate-200">
        <Row label="Material hash">
          <span className="break-all font-mono text-xs">{hash || "n/a"}</span>
        </Row>
        <Row label="Valid until">
          {audit?.valid_until ? formatDate(audit.valid_until) : "n/a"}
          {stale ? <span className="badge badge-queued ml-2">stale</span> : null}
        </Row>
        <Row label="Report date">{audit?.report_date ? formatDateTime(audit.report_date) : "n/a"}</Row>
        <Row label="Session">
          <span className="break-all font-mono text-xs">{report.session_id}</span>
        </Row>
        {auditId ? (
          <Row label="Audit id">
            <span className="break-all font-mono text-xs">{auditId}</span>
          </Row>
        ) : null}
        {generator ? <Row label="Generator">{generator}</Row> : null}
      </dl>

      {!rulesOnly ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Card title="Bias check">
            <div className="font-mono text-sm text-slate-900">{audit?.bias_check?.bias_check ?? "n/a"}</div>
            {audit?.bias_check?.flags && audit.bias_check.flags.length > 0 ? (
              <div className="text-xs text-amber-700">{audit.bias_check.flags.join(", ")}</div>
            ) : null}
          </Card>
          <Card title="Reproducer">
            <div className="font-mono text-sm text-slate-900">
              {audit?.reproducer_verified ? "verified" : "not verified"}
            </div>
            {audit?.reproducer_note ? (
              <div className="text-xs text-slate-600">{audit.reproducer_note}</div>
            ) : null}
          </Card>
          <Card title="Negative evidence" wide>
            <div className="text-xs text-slate-700">
              {evidence && evidence.length > 0
                ? `${evidence.length} checked-but-not-found CWEs`
                : "n/a"}
            </div>
            {evidence && evidence.length > 0 ? (
              <ul className="mt-1 list-disc pl-4 text-xs text-slate-700">
                {evidence.slice(0, 8).map((e) => (
                  <li key={e.cwe}>
                    <span className="font-mono">{e.cwe}</span> — {e.reason}
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>
        </div>
      ) : null}
    </div>
  );
}

/* ----------------------------------------------------------------------------
 * Tabs (wide screens) / accordion (phones)
 * -------------------------------------------------------------------------- */

export default function ReportTabs({ report }: { report: Report }) {
  const narrow = useIsNarrow();
  const baseId = useId();
  const [active, setActive] = useState<TabId>("summary");
  const [open, setOpen] = useState<ReadonlySet<TabId>>(() => new Set<TabId>(["summary"]));
  const tabRefs = useRef<Partial<Record<TabId, HTMLButtonElement | null>>>({});

  const model = useMemo(() => {
    const risks = readRisks(report);
    const runbook = readRunbook(report);
    return {
      risks,
      runbook,
      runbookMarkdown: extractSection(report.final_markdown, "RUNBOOK"),
      stale: isStale(report),
      rulesOnly: report.mode === "static",
    };
  }, [report]);

  const tabs: { id: TabId; label: string }[] = [
    { id: "summary", label: "Summary" },
    { id: "risks", label: `Risks${model.risks.length ? ` (${model.risks.length})` : ""}` },
    { id: "runbook", label: `Runbook${model.runbook.length ? ` (${model.runbook.length})` : ""}` },
    { id: "audit", label: "Audit" },
    { id: "raw", label: "Full report" },
  ];

  function openFull() {
    setActive("raw");
    setOpen((current) => new Set(current).add("raw"));
  }

  function panel(id: TabId): ReactNode {
    switch (id) {
      case "summary":
        return (
          <SummaryPanel
            report={report}
            risks={model.risks}
            runbook={model.runbook}
            stale={model.stale}
            rulesOnly={model.rulesOnly}
            onOpenFull={openFull}
          />
        );
      case "risks":
        return <RisksPanel risks={model.risks} />;
      case "runbook":
        return <RunbookPanel runbook={model.runbook} fallbackMarkdown={model.runbookMarkdown} />;
      case "audit":
        return <AuditPanel report={report} stale={model.stale} rulesOnly={model.rulesOnly} />;
      case "raw":
        return <Markdown>{report.final_markdown}</Markdown>;
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    setActive(tabs[next].id);
    tabRefs.current[tabs[next].id]?.focus();
  }

  if (narrow) {
    return (
      <div className="divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
        {tabs.map((tab) => {
          const expanded = open.has(tab.id);
          return (
            <section key={tab.id}>
              <h2>
                <button
                  type="button"
                  id={`${baseId}-h-${tab.id}`}
                  aria-expanded={expanded}
                  aria-controls={`${baseId}-p-${tab.id}`}
                  onClick={() =>
                    setOpen((current) => {
                      const next = new Set(current);
                      if (next.has(tab.id)) next.delete(tab.id);
                      else next.add(tab.id);
                      return next;
                    })
                  }
                  className="flex min-h-12 w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold text-slate-900"
                >
                  {tab.label}
                  <ChevronDown
                    className={`h-4 w-4 shrink-0 text-slate-500 transition-transform ${expanded ? "rotate-180" : ""}`}
                    aria-hidden="true"
                  />
                </button>
              </h2>
              {expanded ? (
                <div
                  id={`${baseId}-p-${tab.id}`}
                  role="region"
                  aria-labelledby={`${baseId}-h-${tab.id}`}
                  className="px-4 pb-4"
                >
                  {panel(tab.id)}
                </div>
              ) : null}
            </section>
          );
        })}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div role="tablist" aria-label="Report sections" className="flex gap-1 overflow-x-auto border-b border-slate-200 px-2 pt-2">
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(node) => {
                tabRefs.current[tab.id] = node;
              }}
              type="button"
              role="tab"
              id={`${baseId}-t-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${baseId}-p-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActive(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
              className={`-mb-px whitespace-nowrap rounded-t-lg border border-b-0 px-4 py-2 text-sm transition-colors ${
                selected
                  ? "border-slate-200 bg-white font-semibold text-slate-900"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`${baseId}-p-${active}`}
        aria-labelledby={`${baseId}-t-${active}`}
        tabIndex={0}
        className="p-6 outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
      >
        {panel(active)}
      </div>
    </div>
  );
}

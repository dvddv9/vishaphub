import type { Report } from "./types";

/**
 * Pure helpers that turn the flat pipeline result into the pieces the report tabs
 * show. Every reader is tolerant: the result has a different shape for an emergency
 * stop, a rules-only run and a full LLM run, and any field may be missing.
 */

export type Level = "critical" | "high" | "medium" | "low" | "unknown";

export interface RiskRow {
  id: string;
  cwe: string;
  /** The priority exactly as the pipeline wrote it (Russian or English). */
  priority: string;
  level: Level;
  axis: string;
  confidence: string;
  note: string;
}

export interface RunbookEntry {
  cwe: string;
  title: string;
  severity: string;
  immediate: string[];
  shortTerm: string[];
  longTerm: string[];
  escalation: string;
}

const LEVELS: Record<string, Level> = {
  критично: "critical",
  критический: "critical",
  critical: "critical",
  высокий: "high",
  высокая: "high",
  high: "high",
  средний: "medium",
  средняя: "medium",
  medium: "medium",
  низкий: "low",
  низкая: "low",
  low: "low",
};

export function levelOf(priority: unknown): Level {
  if (typeof priority !== "string") return "unknown";
  return LEVELS[priority.trim().toLowerCase()] ?? "unknown";
}

function text(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return "";
}

function confidenceText(value: unknown): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value >= 0 && value <= 1 ? value.toFixed(2) : String(value);
  }
  return text(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

/** Risk rows from the analyst's `risk_nodes`; falls back to the bare CWE list. */
export function readRisks(report: Report): RiskRow[] {
  const stage2 = report.stage2;
  const nodes = isRecord(stage2) && Array.isArray(stage2.risk_nodes) ? stage2.risk_nodes : [];
  const rows: RiskRow[] = [];
  nodes.forEach((node, index) => {
    if (!isRecord(node)) return;
    const priority = text(node.priority) || text(node.severity);
    rows.push({
      id: text(node.id) || `R-${index + 1}`,
      cwe: text(node.cwe),
      priority,
      level: levelOf(priority),
      axis: text(node.axis),
      confidence: confidenceText(node.confidence),
      note: text(node.note) || text(node.title) || text(node.reason) || text(node.description),
    });
  });
  if (rows.length > 0) return rows;

  const cweIds = strings(report.audit?.cwe_ids);
  return cweIds.map((cwe, index) => ({
    id: `C-${index + 1}`,
    cwe,
    priority: "",
    level: "unknown" as Level,
    axis: "",
    confidence: "",
    note: "",
  }));
}

export function countLevels(rows: RiskRow[]): { critical: number; important: number } {
  return {
    critical: rows.filter((r) => r.level === "critical").length,
    important: rows.filter((r) => r.level === "high" || r.level === "medium").length,
  };
}

/** Runbook entries from `audit.runbook` ({"CWE-89": {title, immediate, ...}}). */
export function readRunbook(report: Report): RunbookEntry[] {
  const raw = report.audit?.runbook;
  if (!isRecord(raw)) return [];
  return Object.entries(raw)
    .filter(([, entry]) => isRecord(entry))
    .map(([cwe, entry]) => {
      const e = entry as Record<string, unknown>;
      return {
        cwe,
        title: text(e.title),
        severity: text(e.severity),
        immediate: strings(e.immediate),
        shortTerm: strings(e.short_term),
        longTerm: strings(e.long_term),
        escalation: text(e.escalation),
      };
    });
}

/**
 * The text under a `[TAG]` marker in the written report, up to the next marker.
 * Markers sit at the start of a line: `[CONCLUSION]`, `[RUNBOOK]`, `[AUDIT_TRAIL]`.
 */
export function extractSection(markdown: string, tag: string): string {
  const marker = new RegExp(`^\\[${tag}\\][^\\n]*\\n?`, "m");
  const start = marker.exec(markdown);
  if (!start) return "";
  const rest = markdown.slice(start.index + start[0].length);
  const next = /^\[[A-Z][A-Z0-9_:. -]*\]/m.exec(rest);
  return (next ? rest.slice(0, next.index) : rest).trim();
}

/** `stale` from the server, or computed here for a copy cached before the field existed. */
export function isStale(report: Report, now: number = Date.now()): boolean {
  if (typeof report.stale === "boolean") return report.stale;
  const raw = report.audit?.valid_until;
  if (typeof raw !== "string") return false;
  const when = Date.parse(raw);
  return Number.isFinite(when) && when < now;
}

export function trimTo(value: string, max: number): string {
  if (value.length <= max) return value;
  const cut = value.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`;
}

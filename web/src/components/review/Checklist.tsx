"use client";

import { useEffect, useRef } from "react";
import { PRIORITY, whereLabel } from "@/lib/review-client";
import type { Dispute, EscalationRequest, Finding, Level, Person } from "@/lib/types";
import { type DecideFn, DecisionControls, DecisionTag } from "./DecisionControls";
import { type EscalateFn, EscalationBox } from "./EscalationBox";
import { ChevronIcon } from "../Icons";

export type RowState = { done: boolean; apply: boolean; dispute: string; language: string; disputing: boolean };
export const emptyRow = (): RowState => ({ done: false, apply: false, dispute: "", language: "", disputing: false });

const LEVEL_ORDER: Level[] = ["blocker", "warning", "advisory"];
const PILL: Record<Level, string> = {
  blocker: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)] ring-[var(--vt-blocker)]/30",
  warning: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)] ring-[var(--vt-warning)]/30",
  advisory: "bg-[var(--vt-advisory-bg)] text-[var(--vt-advisory)] ring-[var(--vt-advisory)]/30",
};
const DISPUTE_TEXT: Record<Dispute["status"], string> = {
  queued: "Re-evaluation queued",
  running: "Being re-evaluated",
  upheld: "Re-evaluated: the finding stands",
  overturned: "Re-evaluated: cleared",
  escalated: "Sent to the social media manager",
};

export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level)
    || (b.confidence - a.confidence));
}

export function PriorityPill({ level }: { level: Level }) {
  const p = PRIORITY[level];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ring-1 ring-inset ${PILL[level]}`}
      title={p.label}>
      {p.code}<span className="font-medium">{p.label}</span>
    </span>
  );
}

export function Checklist({ findings, rows, onRow, disputes, active, onSelect, decide, canDismissBlockers = false,
  people = new Map(), creator = true, escalations = {}, onEscalate, onEscalationChanged = () => {} }: {
  findings: Finding[];
  rows: Record<number, RowState>;
  onRow: (id: number, patch: Partial<RowState>) => void;
  disputes: Record<number, Dispute>;
  active: number | null;
  /** The open finding is the selected one: picking a highlight in the text opens its row, and back. */
  onSelect: (id: number | null) => void;
  /** The brand team's accept/dismiss/escalate; absent on the creator's side. */
  decide?: DecideFn;
  canDismissBlockers?: boolean;
  people?: Map<number, Person>;
  /** The creator's own tools: ticking done, applying fixes, disputing. Hidden for the brand team. */
  creator?: boolean;
  /** Requests for a person to review a finding, by finding id. */
  escalations?: Record<number, EscalationRequest>;
  onEscalate?: EscalateFn;
  onEscalationChanged?: () => void;
}) {
  const list = useRef<HTMLUListElement>(null);
  // A highlight picked in the text opens its row here; bring that row into view too.
  useEffect(() => {
    if (active == null) return;
    list.current?.querySelector(`[data-finding="${active}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);
  const counts = LEVEL_ORDER.map((l) => findings.filter((f) => f.level === l).length);
  const done = findings.filter((f) => rows[f.id]?.done).length;
  // Fixes that land in the text itself; a change inside an attachment has to be made by hand.
  const fixable = findings.filter((f) => f.suggestions[0] && (f.source ?? "body") === "body");
  const allApplied = fixable.length > 0 && fixable.every((f) => rows[f.id]?.apply);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {LEVEL_ORDER.map((l, i) => counts[i] > 0 && (
          <span key={l} className="inline-flex items-center gap-1.5"><PriorityPill level={l} /><span className="tabular-nums text-muted">{counts[i]}</span></span>
        ))}
        {creator && (
          <span className="ml-auto flex items-center gap-3">
            {fixable.length > 1 && (
              <button type="button" onClick={() => fixable.forEach((f) => onRow(f.id, { apply: !allApplied }))}
                className="font-medium text-accent hover:underline">
                {allApplied ? "Unselect fixes" : `Apply all ${fixable.length} fixes`}
              </button>
            )}
            <span className="tabular-nums text-subtle">{done}/{findings.length} done</span>
          </span>
        )}
      </div>
      {/* Rows run edge to edge inside the parent card, split by hairlines: a card in a card adds depth, not meaning. */}
      <ul ref={list} className="vt-stagger -mx-4 border-t border-line">
          {findings.map((f) => {
            const row = rows[f.id] ?? emptyRow();
            const isOpen = active === f.id;
            const d = disputes[f.id];
            const s = f.suggestions[0];
            const fixable = Boolean(s) && (f.source ?? "body") === "body";
            return (
              <li key={f.id} data-finding={f.id} className={`border-b border-line transition-colors last:border-0 ${isOpen ? "bg-accent/[0.05]" : "hover:bg-sunken/40"}`}>
                <div className={`grid items-start gap-x-3 px-4 py-3 ${creator ? "grid-cols-[1.25rem_minmax(0,1fr)]" : "grid-cols-1"}`}>
                  {creator && (
                    <input type="checkbox" checked={row.done} onChange={(e) => onRow(f.id, { done: e.target.checked })}
                      aria-label={`Mark "${f.title}" as done`} className="mt-1 h-4 w-4 accent-[var(--vt-accent)]" />
                  )}
                  <button type="button" onClick={() => onSelect(isOpen ? null : f.id)} aria-expanded={isOpen}
                    aria-controls={`finding-${f.id}`} className="group flex min-w-0 flex-col items-start gap-1.5 text-left">
                    <span className="flex w-full items-center gap-2">
                      <PriorityPill level={f.level} />
                      <ChevronIcon size={14} className={`ml-auto shrink-0 text-subtle transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
                    </span>
                    <span className={`line-clamp-2 text-sm font-medium group-hover:text-accent ${row.done ? "text-muted line-through" : ""}`}>{f.title}</span>
                    {/* The fix, readable without opening the row: most decisions need nothing more. */}
                    {s && !isOpen && (
                      <span className="flex w-full min-w-0 items-baseline gap-1.5 text-xs">
                        <del className="truncate text-[var(--vt-blocker)] decoration-1">{s.original}</del>
                        <span aria-hidden className="text-subtle">→</span>
                        <ins className="truncate text-[var(--vt-ok)] no-underline">{s.proposed}</ins>
                      </span>
                    )}
                    <span className="flex flex-wrap gap-x-2 text-xs text-muted">
                      <span>{whereLabel(f)}</span>
                      {row.apply && <span className="font-medium text-[var(--vt-ok)]">· Fix will be applied</span>}
                      {d && <span className="text-accent">· {DISPUTE_TEXT[d.status]}</span>}
                      {f.assessment?.outcome && <span>· {f.assessment.outcome}</span>}
                      <DecisionTag f={f} />
                      {escalations[f.id]?.status === "open" && <span className="font-medium text-accent">· With the brand team</span>}
                    </span>
                  </button>
                </div>
                <div id={`finding-${f.id}`} className="vt-expand" data-open={isOpen} inert={!isOpen}>
                  <div>
                  <div className={`flex flex-col gap-3 pb-4 pr-4 ${creator ? "pl-12" : "pl-4"}`}>
                    <p className="text-sm leading-6 text-ink/90">{f.explanation}</p>
                    {/* A passage in the text is already highlighted there; only attachment quotes need repeating. */}
                    {f.quote && (f.source ?? "body") !== "body" && (
                      <p className="border-l-2 border-line-strong pl-3 text-sm text-muted">“{f.quote}”</p>
                    )}
                    {/* A cross-source finding: the other places the same thing reads differently. */}
                    {(f.locator?.evidence?.length ?? 0) > 0 && (
                      <div className="border-l-2 border-line-strong pl-3 text-sm">
                        <p className="text-xs font-medium text-muted">Compared with</p>
                        <ul className="mt-0.5 flex flex-col gap-0.5">
                          {f.locator!.evidence!.map((e, i) => (
                            <li key={i}><span className="text-muted">{whereLabel({ source: e.source, locator: { time: e.time } })}:</span> “{e.quote}”</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {s && (
                      <div className="border-l-2 border-[var(--vt-ok)] pl-3 text-sm">
                        <p className="text-xs font-medium text-muted">{fixable ? "Suggested fix" : "Suggested change (in the attachment)"}</p>
                        <p className="mt-0.5"><del className="text-[var(--vt-blocker)] decoration-1">{s.original}</del> → <ins className="text-[var(--vt-ok)] no-underline">{s.proposed}</ins></p>
                        {fixable && creator && (
                          <label className="mt-2 flex items-center gap-2 text-xs">
                            <input type="checkbox" checked={row.apply} onChange={(e) => onRow(f.id, { apply: e.target.checked })}
                              className="h-4 w-4 accent-[var(--vt-accent)]" />
                            Apply on resubmit
                          </label>
                        )}
                      </div>
                    )}
                    {f.assessment?.reader_reading && (
                      <p className="border-l-2 border-accent/40 pl-3 text-xs leading-5">
                        <span className="font-semibold">How a reader may take it:</span> {f.assessment.reader_reading}
                        {f.assessment.suggestion && <><br /><span className="font-semibold">Try instead:</span> {f.assessment.suggestion}</>}
                      </p>
                    )}
                    {/* Where the finding comes from: every one cites a rule or an approved fact. */}
                    <ul className="flex flex-col gap-1 text-xs">
                      {f.citations.map((c) => (
                        <li key={`${c.kind}-${c.id}`} className="flex gap-1.5">
                          <span className="shrink-0 rounded bg-sunken px-1.5 font-medium capitalize text-muted">{c.kind}</span>
                          <span>{c.label}{c.source && <span className="text-muted"> · {c.source}</span>}</span>
                        </li>
                      ))}
                      <li className="text-subtle">
                        <span className="capitalize">{f.category}</span> · {Math.round(f.confidence * 100)}% sure · {f.model ? f.model : "rule-based"}
                        {f.signature_valid && " · signed"}
                      </li>
                    </ul>
                    {d?.verdict?.reason && (
                      <p className="rounded-lg border border-accent/30 bg-accent/5 p-2.5 text-xs">
                        <span className="font-semibold">{DISPUTE_TEXT[d.status]}.</span> {d.verdict.reason}
                        {d.verdict.safer_alternative && <><br /><span className="font-semibold">Safer wording:</span> {d.verdict.safer_alternative}</>}
                      </p>
                    )}
                    <DecisionControls f={f} decide={decide} canDismissBlockers={canDismissBlockers} people={people} />
                    <EscalationBox f={f} request={escalations[f.id]} side={creator ? "creator" : "manager"}
                      onEscalate={creator && f.level !== "advisory" ? onEscalate : undefined} onChanged={onEscalationChanged} />
                    {creator && !d && (row.disputing ? (
                      <div className="flex flex-col gap-2">
                        <label className="text-xs font-medium" htmlFor={`dispute-${f.id}`}>What does it actually mean, and why is this reading wrong?</label>
                        <textarea id={`dispute-${f.id}`} value={row.dispute} maxLength={2000}
                          onChange={(e) => onRow(f.id, { dispute: e.target.value })}
                          className="vt-input min-h-16"
                          placeholder="e.g. In Marathi 'bhari' means excellent, not heavy" />
                        <div className="flex flex-wrap items-center gap-2">
                          <input value={row.language} maxLength={60} onChange={(e) => onRow(f.id, { language: e.target.value })}
                            placeholder="Language (optional)" className="vt-input w-44 py-1.5 text-xs" />
                          <span className="text-[11px] text-muted">
                            {row.dispute.trim().length < 10
                              ? `${10 - row.dispute.trim().length} more character${10 - row.dispute.trim().length === 1 ? "" : "s"}`
                              : "Sent with the resubmission"}
                          </span>
                          <button type="button" onClick={() => onRow(f.id, { disputing: false, dispute: "" })} className="ml-auto text-xs text-muted hover:text-ink">Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <button type="button" onClick={() => onRow(f.id, { disputing: true })} className="vt-btn vt-btn-quiet self-start vt-btn-sm">
                        Dispute
                      </button>
                    ))}
                  </div>
                  </div>
                </div>
              </li>
            );
          })}
      </ul>
    </div>
  );
}

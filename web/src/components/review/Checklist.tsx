"use client";

import { useState } from "react";
import { PRIORITY, whereLabel } from "@/lib/review-client";
import type { Dispute, Finding, Level } from "@/lib/types";

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

export function Checklist({ findings, rows, onRow, disputes, active, onSelect }: {
  findings: Finding[];
  rows: Record<number, RowState>;
  onRow: (id: number, patch: Partial<RowState>) => void;
  disputes: Record<number, Dispute>;
  active: number | null;
  onSelect: (id: number) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const counts = LEVEL_ORDER.map((l) => findings.filter((f) => f.level === l).length);
  const done = findings.filter((f) => rows[f.id]?.done).length;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {LEVEL_ORDER.map((l, i) => counts[i] > 0 && (
          <span key={l} className="inline-flex items-center gap-1.5"><PriorityPill level={l} /><span className="tabular-nums text-muted">{counts[i]}</span></span>
        ))}
        <span className="ml-auto tabular-nums text-subtle">{done}/{findings.length} done</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-line bg-raised">
        <ul className="vt-stagger">
          {findings.map((f) => {
            const row = rows[f.id] ?? emptyRow();
            const isOpen = open === f.id;
            const d = disputes[f.id];
            const s = f.suggestions[0];
            const fixable = Boolean(s) && (f.source ?? "body") === "body";
            return (
              <li key={f.id} className={`border-b border-line transition-colors last:border-0 ${active === f.id ? "bg-accent/[0.06]" : "hover:bg-sunken/40"}`}>
                <div className="grid grid-cols-[2.5rem_minmax(0,1fr)] items-start gap-x-3 gap-y-1 px-3 py-2.5 md:grid-cols-[2.5rem_6.5rem_minmax(0,1fr)]">
                  <input type="checkbox" checked={row.done} onChange={(e) => onRow(f.id, { done: e.target.checked })}
                    aria-label={`Mark "${f.title}" as done`} className="mt-1 h-4 w-4 accent-[var(--vt-accent)]" />
                  <div className="md:contents">
                    <div className="mb-1 md:mb-0 md:pt-0.5"><PriorityPill level={f.level} /></div>
                    <button type="button" onClick={() => { setOpen(isOpen ? null : f.id); onSelect(f.id); }}
                      aria-expanded={isOpen} className="group min-w-0 text-left">
                      <span className={`line-clamp-2 text-sm font-medium group-hover:text-accent ${row.done ? "text-muted line-through" : ""}`}>{f.title}</span>
                      <span className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-muted">
                        <span>{whereLabel(f)}</span>
                        {d && <span className="text-accent">· {DISPUTE_TEXT[d.status]}</span>}
                        {f.assessment?.outcome && <span>· {f.assessment.outcome}</span>}
                      </span>
                    </button>
                  </div>
                </div>
                {isOpen && (
                  <div className="vt-pop flex flex-col gap-3 border-t border-line px-4 py-3 md:pl-[3.25rem]">
                    <p className="text-sm leading-6 text-ink/90">{f.explanation}</p>
                    {f.quote && <p className="rounded-lg bg-sunken px-3 py-2 text-sm text-muted">“{f.quote}”</p>}
                    <p className="text-xs text-subtle">
                      <span className="capitalize">{f.category}</span> · {Math.round(f.confidence * 100)}% · {f.model ? f.model : "rule-based"}
                      {f.signature_valid && " · signed"}
                    </p>
                    {f.citations.map((c) => (
                      <p key={`${c.kind}-${c.id}`} className="text-xs">
                        <span className="mr-1.5 rounded-md bg-sunken px-1.5 py-0.5 font-medium capitalize text-muted">{c.kind}</span>
                        {c.label}{c.source && <span className="text-muted"> · {c.source}</span>}
                      </p>
                    ))}
                    {f.assessment?.reader_reading && (
                      <p className="rounded-lg border border-line p-2.5 text-xs">
                        <span className="font-semibold">How a reader may take it:</span> {f.assessment.reader_reading}
                        {f.assessment.suggestion && <><br /><span className="font-semibold">Try instead:</span> {f.assessment.suggestion}</>}
                      </p>
                    )}
                    {s && (
                      <div className="rounded-lg border border-line p-2.5 text-sm">
                        <p className="text-xs font-medium text-muted">{fixable ? "Suggested fix" : "Suggested change (in the attachment)"}</p>
                        <p className="mt-1"><del className="text-[var(--vt-blocker)]">{s.original}</del> → <ins className="text-[var(--vt-ok)] no-underline">{s.proposed}</ins></p>
                        {fixable && (
                          <label className="mt-2 flex items-center gap-2 text-xs">
                            <input type="checkbox" checked={row.apply} onChange={(e) => onRow(f.id, { apply: e.target.checked })}
                              className="h-4 w-4 accent-[var(--vt-accent)]" />
                            Apply on resubmit
                          </label>
                        )}
                      </div>
                    )}
                    {d?.verdict?.reason && (
                      <p className="rounded-lg border border-accent/30 bg-accent/5 p-2.5 text-xs">
                        <span className="font-semibold">{DISPUTE_TEXT[d.status]}.</span> {d.verdict.reason}
                        {d.verdict.safer_alternative && <><br /><span className="font-semibold">Safer wording:</span> {d.verdict.safer_alternative}</>}
                      </p>
                    )}
                    {!d && (row.disputing ? (
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
                      <button type="button" onClick={() => onRow(f.id, { disputing: true })} className="vt-btn vt-btn-quiet self-start py-1.5 text-xs">
                        Dispute
                      </button>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

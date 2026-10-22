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
        {LEVEL_ORDER.map((l, i) => (
          <span key={l} className="inline-flex items-center gap-1.5"><PriorityPill level={l} /> {counts[i]}</span>
        ))}
        <span className="ml-auto text-muted">{done} of {findings.length} marked done</span>
      </div>
      <div className="overflow-hidden rounded-xl border border-line">
        <div className="hidden grid-cols-[2.5rem_6.5rem_minmax(0,1fr)] gap-3 border-b border-line bg-bg px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-muted md:grid">
          <span>Done</span><span>Priority</span><span>Issue and where it is</span>
        </div>
        <ul>
          {findings.map((f) => {
            const row = rows[f.id] ?? emptyRow();
            const isOpen = open === f.id;
            const d = disputes[f.id];
            const s = f.suggestions[0];
            const fixable = Boolean(s) && (f.source ?? "body") === "body";
            return (
              <li key={f.id} className={`border-b border-line last:border-0 ${active === f.id ? "bg-accent/5" : ""}`}>
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
                  <div className="flex flex-col gap-3 border-t border-dashed border-line bg-bg/60 px-4 py-3 md:pl-[3.25rem]">
                    <p className="text-sm font-semibold">{f.title}</p>
                    <p className="text-sm text-ink/90">{f.explanation}</p>
                    {f.quote && <blockquote className="border-l-2 border-line pl-3 text-sm italic text-muted">“{f.quote}”</blockquote>}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
                      <span className="capitalize">{f.category}</span>
                      <span>confidence {Math.round(f.confidence * 100)}%</span>
                      <span>{f.model ? `judged by ${f.model}` : "rule-based, no model"}</span>
                      {f.signature_valid && <span className="text-[var(--vt-ok)]">signed</span>}
                    </div>
                    {f.citations.map((c) => (
                      <p key={`${c.kind}-${c.id}`} className="text-xs">
                        <span className="mr-1 rounded bg-surface px-1.5 py-0.5 font-medium uppercase text-muted">{c.kind}</span>
                        {c.label}{c.source && <span className="text-muted"> · {c.source}</span>}
                      </p>
                    ))}
                    {f.assessment?.reader_reading && (
                      <p className="rounded-lg border border-line bg-surface p-2.5 text-xs">
                        <span className="font-semibold">How a reader may take it:</span> {f.assessment.reader_reading}
                        {f.assessment.suggestion && <><br /><span className="font-semibold">Try instead:</span> {f.assessment.suggestion}</>}
                      </p>
                    )}
                    {s && (
                      <div className="rounded-lg border border-line bg-surface p-2.5 text-sm">
                        <p className="text-xs font-medium text-muted">{fixable ? "Suggested fix" : "Suggested change (edit the image, page or video)"}</p>
                        <p className="mt-1"><del className="text-[var(--vt-blocker)]">{s.original}</del> → <ins className="text-[var(--vt-ok)] no-underline">{s.proposed}</ins></p>
                        {fixable && (
                          <label className="mt-2 flex items-center gap-2 text-xs">
                            <input type="checkbox" checked={row.apply} onChange={(e) => onRow(f.id, { apply: e.target.checked })}
                              className="h-4 w-4 accent-[var(--vt-accent)]" />
                            Apply this fix when I resubmit
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
                          className="min-h-16 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
                          placeholder="e.g. In Marathi 'bhari' means excellent, not heavy" />
                        <div className="flex flex-wrap items-center gap-2">
                          <input value={row.language} maxLength={60} onChange={(e) => onRow(f.id, { language: e.target.value })}
                            placeholder="Language (optional)" className="w-44 rounded-lg border border-line bg-surface px-3 py-1.5 text-xs" />
                          <span className="text-[11px] text-muted">
                            {row.dispute.trim().length < 10
                              ? `A few more words, please: ${10 - row.dispute.trim().length} more character${10 - row.dispute.trim().length === 1 ? "" : "s"} before it can be sent.`
                              : "Sent with the resubmission. Prism re-reads it layer by layer and can still say no."}
                          </span>
                          <button type="button" onClick={() => onRow(f.id, { disputing: false, dispute: "" })} className="ml-auto text-xs text-muted hover:text-ink">Cancel</button>
                        </div>
                      </div>
                    ) : (
                      <button type="button" onClick={() => onRow(f.id, { disputing: true })}
                        className="self-start rounded-lg border border-line bg-surface px-3 py-1.5 text-xs font-medium hover:border-accent">
                        This isn’t what it means…
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

"use client";

import { useState } from "react";
import { relativeTime } from "@/lib/review-client";
import type { Decision, Finding, Person } from "@/lib/types";

// What a dismissal means. These codes feed guideline health: "guideline unclear"
// and false positives are how a rule earns a rewrite.
export const REASONS = [
  { code: "false_positive", label: "Not actually an issue" },
  { code: "not_applicable", label: "Rule doesn't apply here" },
  { code: "guideline_unclear", label: "The guideline is unclear" },
  { code: "intentional", label: "Intentional, approved exception" },
  { code: "other", label: "Other" },
] as const;
const REASON_LABEL: Record<string, string> = Object.fromEntries(REASONS.map((r) => [r.code, r.label]));

export const ACTION_LABEL: Record<Decision["action"], string> = {
  accepted: "Confirmed",
  rejected: "Dismissed",
  edited: "Edited",
  escalated: "Escalated",
};
const ACTION_TONE: Record<Decision["action"], string> = {
  accepted: "text-[var(--vt-blocker)]",
  rejected: "text-[var(--vt-ok)]",
  edited: "text-accent",
  escalated: "text-[var(--vt-warning)]",
};

export type DecideFn = (f: Finding, action: Decision["action"], reasonCode?: string | null, reasonText?: string | null) => Promise<void>;

/** The latest human call on a finding, as a short tag for the collapsed row. */
export function DecisionTag({ f }: { f: Finding }) {
  const d = f.decisions.at(-1);
  if (!d) return null;
  return <span className={`font-medium ${ACTION_TONE[d.action]}`}>· {ACTION_LABEL[d.action]}</span>;
}

/**
 * The brand team's call on one finding. Confirming keeps it in force; dismissing
 * (with a reason) clears it for approval and teaches guideline health; escalating
 * hands it to an approver. Every call is kept, newest last, in the audit log too.
 */
export function DecisionControls({ f, decide, canDismissBlockers, people }: {
  f: Finding;
  /** Absent for creators: they see the brand team's calls but don't make them. */
  decide?: DecideFn;
  canDismissBlockers: boolean;
  people: Map<number, Person>;
}) {
  const [dismissing, setDismissing] = useState(false);
  const [code, setCode] = useState<string>("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const blockedDismiss = f.level === "blocker" && !canDismissBlockers;

  if (!decide && f.decisions.length === 0) return null;
  const run = async (action: Decision["action"], reasonCode?: string, reasonText?: string) => {
    if (!decide) return;
    setBusy(true);
    try {
      await decide(f, action, reasonCode, reasonText);
      setDismissing(false);
      setCode("");
      setNote("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-line p-2.5">
      <p className="text-xs font-medium text-muted">Brand team decision</p>
      {f.decisions.length > 0 && (
        <ul className="mt-1.5 flex flex-col gap-1">
          {f.decisions.map((d) => (
            <li key={d.id} className="text-xs">
              <span className={`font-semibold ${ACTION_TONE[d.action]}`}>{ACTION_LABEL[d.action]}</span>
              <span className="text-muted"> by {people.get(d.actor_id)?.name ?? "a reviewer"} · {relativeTime(d.created_at)}</span>
              {d.reason_code && <span className="text-muted"> · {REASON_LABEL[d.reason_code] ?? d.reason_code}</span>}
              {d.reason_text && <span className="block text-subtle">&ldquo;{d.reason_text}&rdquo;</span>}
            </li>
          ))}
        </ul>
      )}
      {!decide ? null : dismissing ? (
        <div className="vt-pop mt-2 flex flex-col gap-2">
          <label className="text-xs font-medium" htmlFor={`reason-${f.id}`}>Why dismiss it?</label>
          <select id={`reason-${f.id}`} value={code} onChange={(e) => setCode(e.target.value)} className="vt-input py-1.5 text-xs">
            <option value="" disabled>Choose a reason</option>
            {REASONS.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
          </select>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Note for the creator and the audit log (optional)"
            aria-label="Note" className="vt-input min-h-14 text-xs" />
          <div className="flex items-center gap-2">
            <button type="button" disabled={busy || !code} onClick={() => run("rejected", code, note.trim())}
              className="vt-btn vt-btn-primary px-3 py-1.5 text-xs">Dismiss</button>
            <button type="button" onClick={() => setDismissing(false)} className="vt-btn vt-btn-quiet px-3 py-1.5 text-xs">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <button type="button" disabled={busy} onClick={() => run("accepted")} className="vt-btn vt-btn-quiet px-2.5 py-1 text-xs"
            title="Agree: this must change before it goes out">Confirm</button>
          <button type="button" disabled={busy || blockedDismiss} onClick={() => setDismissing(true)}
            className="vt-btn vt-btn-quiet px-2.5 py-1 text-xs"
            title={blockedDismiss ? "Only approvers can dismiss a must-fix issue" : "Clear it, with a reason"}>Dismiss</button>
          <button type="button" disabled={busy} onClick={() => run("escalated")} className="vt-btn vt-btn-quiet px-2.5 py-1 text-xs"
            title="Hand it to an approver">Escalate</button>
          {blockedDismiss && <span className="text-[11px] text-subtle">Approvers dismiss must-fix issues</span>}
        </div>
      )}
    </div>
  );
}

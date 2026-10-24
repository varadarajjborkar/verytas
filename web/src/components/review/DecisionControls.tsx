"use client";

import { useState } from "react";
import { relativeTime } from "@/lib/review-client";
import type { Decision, Finding, Person } from "@/lib/types";
import { EnterIcon } from "../Icons";

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

/** Where the brand team left a finding: asked to change, kept as it is, or handed to an approver. */
export type CallState = "asked" | "kept" | "escalated";
export function callOf(f: Finding): CallState | null {
  const d = f.decisions.at(-1);
  if (!d) return null;
  return d.action === "rejected" ? "kept" : d.action === "escalated" ? "escalated" : "asked";
}
export const CALL_LABEL: Record<CallState, string> = { asked: "Change asked", kept: "Kept", escalated: "With an approver" };

/** The latest human call on a finding, as a short tag for the collapsed row. */
export function DecisionTag({ f }: { f: Finding }) {
  const d = f.decisions.at(-1);
  if (!d) return null;
  return <span className={`font-medium ${ACTION_TONE[d.action]}`}>· {ACTION_LABEL[d.action]}</span>;
}

/**
 * The brand team's call on one finding. Asking for the change keeps it in force; keeping the words (with a
 * reason, one tap) clears it for approval and teaches guideline health; escalating hands it to an approver.
 * Every call is kept, newest last, in the audit log too, so changing your mind is just another call.
 */
export function DecisionControls({ f, decide, canDismissBlockers, people, onBusy, onDecided }: {
  f: Finding;
  /** Absent for creators: they see the brand team's calls but don't make them. */
  decide?: DecideFn;
  canDismissBlockers: boolean;
  people: Map<number, Person>;
  /** Told when a call starts and ends saving, so the text can animate the words being decided on. */
  onBusy?: (id: number | null) => void;
  onDecided?: (f: Finding) => void;
}) {
  const [keeping, setKeeping] = useState(false);
  const [other, setOther] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [changing, setChanging] = useState(false);
  const blockedDismiss = f.level === "blocker" && !canDismissBlockers;
  const call = callOf(f);
  const fixable = Boolean(f.suggestions[0]) && (f.source ?? "body") === "body";

  if (!decide && f.decisions.length === 0) return null;
  const run = async (action: Decision["action"], reasonCode?: string, reasonText?: string) => {
    if (!decide) return;
    setBusy(true);
    onBusy?.(action === "accepted" && fixable ? f.id : null);
    try {
      await decide(f, action, reasonCode, reasonText);
      setKeeping(false);
      setOther(false);
      setNote("");
      setChanging(false);
      onDecided?.(f);
    } catch {
      // decide() has already told the person; the controls stay as they were.
    } finally {
      setBusy(false);
      onBusy?.(null);
    }
  };

  const history = f.decisions.length > 0 && (
    <ul className="flex flex-col gap-1">
      {f.decisions.map((d) => (
        <li key={d.id} className="text-xs">
          <span className={`font-semibold ${ACTION_TONE[d.action]}`}>{ACTION_LABEL[d.action]}</span>
          <span className="text-muted"> by {people.get(d.actor_id)?.name ?? "a reviewer"} · {relativeTime(d.created_at)}</span>
          {d.reason_code && <span className="text-muted"> · {REASON_LABEL[d.reason_code] ?? d.reason_code}</span>}
          {d.reason_text && <span className="block text-subtle">&ldquo;{d.reason_text}&rdquo;</span>}
        </li>
      ))}
    </ul>
  );

  if (!decide || (call && !changing)) {
    return (
      <div className="flex flex-col gap-2 border-t border-line pt-3">
        {history}
        {decide && (
          <button type="button" onClick={() => setChanging(true)} className="vt-btn vt-btn-xs self-start">
            Change this call
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5 border-t border-line pt-3">
      {history}
      {keeping ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-muted">{f.level === "blocker" ? "Why clear it?" : "Why keep it as is?"}</p>
          {!other ? (
            <div className="flex flex-wrap gap-1.5">
              {REASONS.map((r, i) => (
                <button key={r.code} type="button" disabled={busy}
                  onClick={() => (r.code === "other" ? setOther(true) : run("rejected", r.code))}
                  style={{ animationDelay: `${i * 30}ms` }}
                  className="vt-pop rounded-full border border-line bg-raised px-2.5 py-1 text-xs transition hover:border-accent hover:text-accent disabled:opacity-50">
                  {r.code === "other" ? "Other…" : r.label}
                </button>
              ))}
            </div>
          ) : (
            <div className="vt-pop flex flex-col gap-2">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} autoFocus
                placeholder="Why it can stay (the creator and the audit log see this)" aria-label="Reason" className="vt-input min-h-14 text-xs" />
              <button type="button" disabled={busy || note.trim().length < 3} onClick={() => run("rejected", "other", note.trim())}
                className="vt-btn vt-btn-primary vt-btn-sm self-start">Keep it</button>
            </div>
          )}
          <button type="button" onClick={() => { setKeeping(false); setOther(false); }} className="vt-btn vt-btn-xs self-start">Back</button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-1.5">
          <button type="button" disabled={busy} onClick={() => run("accepted")} data-primary-call
            className="vt-btn vt-btn-primary vt-btn-sm" title="This must change before it goes out">
            {fixable ? "Ask for this fix" : "Ask to fix"}<EnterIcon size={13} className="opacity-60" />
          </button>
          <button type="button" disabled={busy || blockedDismiss} onClick={() => setKeeping(true)} className="vt-btn vt-btn-sm"
            title={blockedDismiss ? "Only approvers can clear a must-fix issue" : "Leave the words, with a reason"}>
            {f.level === "blocker" ? "Clear it…" : "Keep as is"}
          </button>
          <button type="button" disabled={busy} onClick={() => run("escalated")} className="vt-btn vt-btn-quiet vt-btn-sm"
            title="Hand it to an approver">Escalate</button>
          {changing && <button type="button" onClick={() => setChanging(false)} className="vt-btn vt-btn-xs">Cancel</button>}
          {blockedDismiss && <span className="w-full text-[11px] text-subtle">Approvers clear must-fix issues</span>}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { PRIORITY, whereLabel } from "@/lib/review-client";
import type { Dispute, EscalationRequest, Finding, Level, Person } from "@/lib/types";
import { CALL_LABEL, callOf, type CallState, type DecideFn, DecisionControls } from "./DecisionControls";
import { type EscalateFn, EscalationBox } from "./EscalationBox";
import { CheckIcon, ChevronIcon } from "../Icons";
import { reveal } from "@/lib/reveal";
import { shownError } from "@/lib/errors";

export type RowState = { done: boolean; apply: boolean; dispute: string; language: string; disputing: boolean };
export const emptyRow = (): RowState => ({ done: false, apply: false, dispute: "", language: "", disputing: false });

const LEVEL_ORDER: Level[] = ["blocker", "warning", "advisory"];
const PILL: Record<Level, string> = {
  blocker: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)] ring-[var(--vt-blocker)]/30",
  warning: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)] ring-[var(--vt-warning)]/30",
  advisory: "bg-[var(--vt-advisory-bg)] text-[var(--vt-advisory)] ring-[var(--vt-advisory)]/30",
};
const DOT: Record<Level, string> = {
  blocker: "bg-[var(--vt-blocker)]",
  warning: "bg-[var(--vt-warning)]",
  advisory: "bg-[var(--vt-advisory)]",
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

/** Where a row stands. The brand team's call on their side; the creator's own choice (fix, done, dispute) on theirs. */
export type RowCall = { state: CallState | "chosen" | "done" | "disputed"; label: string } | null;
export function rowCall(f: Finding, row: RowState | undefined, creator: boolean): RowCall {
  if (creator) {
    if (row?.apply) return { state: "chosen", label: "Fix chosen" };
    if (row?.done) return { state: "done", label: "Done" };
    if ((row?.dispute ?? "").trim().length >= 10) return { state: "disputed", label: "Disputed" };
    return null;
  }
  const c = callOf(f);
  return c ? { state: c, label: CALL_LABEL[c] } : null;
}

export function Checklist({ findings, rows, onRow, disputes, active, onSelect, decide, canDismissBlockers = false,
  people = new Map(), creator = true, escalations = {}, onEscalate, onDispute, onEscalationChanged = () => {}, show = "all",
  onBusy, onDecided, creatorCalls = creator }: {
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
  /** Sends a dispute now, for Verytas to read again; without it a dispute goes out with the next re-check. */
  onDispute?: (f: Finding, claim: string, language: string | null) => Promise<void>;
  onEscalationChanged?: () => void;
  /** "open" hides rows already decided, except the one being looked at. */
  show?: "all" | "open";
  onBusy?: (id: number | null) => void;
  onDecided?: (f: Finding) => void;
  /** Whose calls mark a row as handled: the creator's own (fix, done, dispute), or the brand team's decisions. */
  creatorCalls?: boolean;
}) {
  const list = useRef<HTMLUListElement>(null);
  // A highlight picked in the text, or the next issue on a walk, opens its row here: bring it into view. A row
  // opened by hand is already under the pointer; it only shows the part that opened below it, never more.
  // The issue opened for the reader on arrival is not a pick, so the page doesn't move for it.
  const arrival = useRef<number | null | undefined>(active);
  useEffect(() => {
    // Closing a row ends the arrival too: opening that issue again is a pick like any other.
    if (active == null) { arrival.current = undefined; return; }
    if (active === arrival.current) return;
    arrival.current = undefined;
    reveal(list.current?.querySelector(`[data-finding="${active}"]`), { page: true, bottom: 96 });
  }, [active]);
  // Fixes that land in the text itself; a change inside an attachment has to be made by hand.
  const fixable = findings.filter((f) => f.suggestions[0] && (f.source ?? "body") === "body");
  const allApplied = fixable.length > 0 && fixable.every((f) => rows[f.id]?.apply);

  return (
    <div className="flex flex-col gap-2">
      {creator && fixable.length > 1 && (
        <button type="button" onClick={() => fixable.forEach((f) => onRow(f.id, { apply: !allApplied }))}
          className="self-end text-xs font-medium text-accent hover:underline">
          {allApplied ? "Unselect fixes" : `Use all ${fixable.length} fixes`}
        </button>
      )}
      <ul ref={list} className="vt-stagger flex flex-col gap-1.5">
          {findings.map((f, i) => {
            const row = rows[f.id] ?? emptyRow();
            const isOpen = active === f.id;
            const call = rowCall(f, rows[f.id], creatorCalls);
            if (show === "open" && call && !isOpen) return null;
            const d = disputes[f.id];
            const s = f.suggestions[0];
            const fixable = Boolean(s) && (f.source ?? "body") === "body";
            const quiet = call?.state === "kept" || call?.state === "done";
            // A withdrawn request is history, so the creator can ask again.
            const raised = escalations[f.id]?.status === "withdrawn" ? undefined : escalations[f.id];
            const canAsk = f.level !== "advisory" && Boolean(onEscalate) && !raised;
            return (
              <li key={f.id} data-finding={f.id}
                className={`rounded-2xl border transition-[border-color,box-shadow,background-color] duration-200 ${isOpen
                  ? "border-accent bg-raised shadow-[0_0_0_3px_color-mix(in_srgb,var(--vt-accent)_16%,transparent)]"
                  : "border-line bg-surface hover:border-line-strong"}`}>
                <button type="button" onClick={() => onSelect(isOpen ? null : f.id)} aria-expanded={isOpen}
                  aria-controls={`finding-${f.id}`} className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left">
                  <span aria-hidden className={`grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full text-[11px] font-bold transition-all duration-300 ${
                    !call ? `${DOT[f.level]} text-white` : quiet ? "scale-90 bg-sunken text-muted ring-1 ring-inset ring-line-strong"
                      : call.state === "escalated" ? "scale-90 bg-[var(--vt-warning)] text-white" : "scale-90 bg-[var(--vt-ok)] text-white"}`}>
                    {!call ? i + 1 : quiet ? "•" : <CheckIcon size={12} strokeWidth={3} />}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className={`truncate text-[13.5px] font-medium ${call ? "text-muted" : ""}`} title={f.title}>{f.title}</span>
                    <span className="truncate text-[11.5px] text-subtle">
                      <span className="capitalize">{f.category}</span> · {whereLabel(f)}
                      {d && <span className="text-accent"> · {DISPUTE_TEXT[d.status]}</span>}
                      {escalations[f.id]?.status === "open" && <span className="text-accent"> · With the brand team</span>}
                    </span>
                  </span>
                  {call ? (
                    <span className={`shrink-0 text-[11.5px] ${quiet ? "text-subtle" : call.state === "escalated" ? "text-[var(--vt-warning)]" : "text-[var(--vt-ok)]"}`}>{call.label}</span>
                  ) : (
                    <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold ${PILL[f.level]}`}>{PRIORITY[f.level].label}</span>
                  )}
                  <ChevronIcon size={14} className={`shrink-0 text-subtle transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`} />
                </button>
                <div id={`finding-${f.id}`} className="vt-expand" data-open={isOpen} inert={!isOpen}>
                  <div>
                  <div className="flex flex-col gap-3 pb-3 pl-[2.6rem] pr-3">
                    <p className="text-[13px] leading-6 text-muted">{f.explanation}</p>
                    {/* A passage in the text is already highlighted there; only attachment quotes need repeating. */}
                    {f.quote && (f.source ?? "body") !== "body" && (
                      <p className="border-l-2 border-line-strong pl-3 text-sm text-muted">“{f.quote}”</p>
                    )}
                    {s && (
                      <div className="rounded-xl bg-sunken px-3 py-2 text-[13px]">
                        {!fixable && <p className="mb-0.5 text-[11px] font-medium text-subtle">Change in the attachment</p>}
                        <del className="text-[var(--vt-blocker)] decoration-1 opacity-85">{s.original}</del>
                        {s.proposed ? <> <span aria-hidden className="text-subtle">→</span> <ins className="font-medium text-[var(--vt-ok)] no-underline">{s.proposed}</ins></>
                          : <span className="text-subtle"> remove</span>}
                      </div>
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
                    {/* Web results for a claim with no approved fact: something to check, never proof by itself. */}
                    {(f.research?.length ?? 0) > 0 && (
                      <div className="border-l-2 border-line-strong pl-3 text-sm">
                        <p className="text-xs font-medium text-muted">Found on the web (not approved)</p>
                        <ul className="mt-0.5 flex flex-col gap-1.5">
                          {f.research!.map((r) => (
                            <li key={r.url}>
                              <a href={r.url} target="_blank" rel="noopener noreferrer nofollow" className="font-medium hover:text-accent">{r.title}</a>
                              <span className="text-xs text-muted"> · {r.site}{r.supports != null && r.supports >= 0.6 ? " · may back the claim" : r.supports != null ? " · doesn't say this" : ""}</span>
                              <span className="block text-xs text-muted line-clamp-2">{r.snippet}</span>
                            </li>
                          ))}
                        </ul>
                        <p className="mt-1 text-xs text-subtle">Only an approved fact backs a claim. A brand admin can add a source to the fact library.</p>
                      </div>
                    )}
                    {/* What reviewers decided before about words like these, so nobody argues the same case twice. */}
                    {(f.precedents?.length ?? 0) > 0 && (
                      <div className="border-l-2 border-line-strong pl-3 text-sm">
                        <p className="text-xs font-medium text-muted">Decided before</p>
                        <ul className="mt-0.5 flex flex-col gap-1">
                          {f.precedents!.map((p) => (
                            <li key={p.finding_id}>
                              <span>{p.summary}</span>
                              <span className="block text-xs text-muted">“{p.quote}”</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {f.assessment?.reader_reading && (
                      <p className="border-l-2 border-accent/40 pl-3 text-xs leading-5">
                        <span className="font-semibold">How a reader may take it:</span> {f.assessment.reader_reading}
                        {f.assessment.suggestion && <><br /><span className="font-semibold">Try instead:</span> {f.assessment.suggestion}</>}
                      </p>
                    )}
                    {/* Where the finding comes from: every one cites a rule or an approved fact. */}
                    <p className="text-[11.5px] leading-5 text-subtle">
                      {f.citations.map((c, i) => (
                        <span key={`${c.kind}-${c.id}`}>{i > 0 && " · "}<span className="capitalize">{c.kind}</span>: {c.label}{c.source && ` (${c.source})`}</span>
                      ))}
                      {f.citations.length > 0 && <br />}
                      {Math.round(f.confidence * 100)}% sure
                      {/* What that certainty has meant here: how often reviewers agreed with findings like it. */}
                      {f.calibration?.agree != null && (
                        <span title={f.calibration.n != null ? `From ${f.calibration.n} decision${f.calibration.n === 1 ? "" : "s"} on ${f.calibration.family === "all" ? "all" : f.calibration.family} findings in this workspace` : undefined}>
                          {" "}(reviewers agreed with {Math.round(f.calibration.agree * 10)} in 10 like it)
                        </span>
                      )}
                      {f.calibration?.held_back_below != null && (
                        <span>{" "}· an advisory: reviewers here dismiss many warnings under {Math.round(f.calibration.held_back_below * 100)}% sure</span>
                      )}
                      {" "}· {f.model ? f.model : "rule-based"}
                      {f.signature_valid && " · signed"}
                    </p>
                    {d && !d.verdict?.reason && (
                      <p role="status" className="rounded-lg border border-accent/30 bg-accent/5 p-2.5 text-xs">
                        <span className="font-semibold">Dispute sent. {DISPUTE_TEXT[d.status]}.</span>{" "}
                        {d.status === "queued" || d.status === "running"
                          ? "Verytas is reading the issue again with your explanation; the result shows here in a moment."
                          : "The brand team has it."}
                      </p>
                    )}
                    {d?.verdict?.reason && (
                      <p className="rounded-lg border border-accent/30 bg-accent/5 p-2.5 text-xs">
                        <span className="font-semibold">{DISPUTE_TEXT[d.status]}.</span> {d.verdict.reason}
                        {d.verdict.safer_alternative && <><br /><span className="font-semibold">Safer wording:</span> {d.verdict.safer_alternative}</>}
                      </p>
                    )}
                    {creator && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {fixable && (
                          <button type="button" onClick={() => onRow(f.id, { apply: !row.apply })}
                            className={`vt-btn vt-btn-sm ${row.apply ? "" : "vt-btn-primary"}`}>
                            {row.apply ? "Don't use this fix" : "Use this fix"}
                          </button>
                        )}
                        <button type="button" onClick={() => onRow(f.id, { done: !row.done })}
                          className={`vt-btn vt-btn-sm ${!fixable && !row.done ? "vt-btn-primary" : ""}`}>
                          {row.done ? "Not done yet" : "Mark done"}
                        </button>
                      </div>
                    )}
                    {/* Disagreeing, on its own quiet line: Verytas looks again (dispute) or a person does (escalation). */}
                    {creator && ((!d && !row.disputing) || canAsk) && (
                      <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-subtle">
                        <span>Think it&apos;s wrong?</span>
                        {!d && !row.disputing && (
                          <button type="button" onClick={() => onRow(f.id, { disputing: true })} className="font-medium text-accent hover:underline">Dispute it</button>
                        )}
                        {!d && !row.disputing && canAsk && <span aria-hidden>·</span>}
                        {canAsk && (
                          <EscalationBox f={f} request={undefined} side="creator" onEscalate={onEscalate} onChanged={onEscalationChanged} />
                        )}
                      </div>
                    )}
                    {creator && !d && row.disputing && (
                      <DisputeForm f={f} row={row} onRow={onRow} onDispute={onDispute} />
                    )}
                    <DecisionControls f={f} decide={decide} canDismissBlockers={canDismissBlockers} people={people}
                      onBusy={onBusy} onDecided={onDecided} />
                    {/* An escalation already raised shows here; asking for one is on the creator's "Think it's wrong?" line. */}
                    {(!creator || raised) && (
                      <EscalationBox f={f} request={escalations[f.id]} side={creator ? "creator" : "manager"}
                        onEscalate={undefined} onChanged={onEscalationChanged} />
                    )}
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

/**
 * "That is not what it means": the creator explains, Verytas reads the issue again with that explanation, and
 * if it still can't tell, a person on the brand team decides. Sent on its own here; the explanation is also
 * kept on the row, so it goes out with the next re-check if it was never sent.
 */
function DisputeForm({ f, row, onRow, onDispute }: {
  f: Finding; row: RowState; onRow: (id: number, patch: Partial<RowState>) => void;
  onDispute?: (f: Finding, claim: string, language: string | null) => Promise<void>;
}) {
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const left = 10 - row.dispute.trim().length;
  async function send() {
    if (!onDispute || left > 0) return;
    setSending(true);
    setFailed(null);
    const claim = row.dispute.trim();
    const language = row.language.trim();
    // Taken off the row while it is sent, so a re-check started meanwhile doesn't file it a second time.
    onRow(f.id, { dispute: "" });
    try {
      await onDispute(f, claim, language || null);
      onRow(f.id, { disputing: false, dispute: "", language: "" });
    } catch (err) {
      onRow(f.id, { dispute: claim });
      setFailed(shownError(err, "The dispute wasn't sent. Try again."));
    } finally {
      setSending(false);
    }
  }
  return (
    <div className="vt-pop flex flex-col gap-2">
      <label className="text-xs font-medium" htmlFor={`dispute-${f.id}`}>Why is this reading wrong?</label>
      <p id={`dispute-help-${f.id}`} className="text-[11px] text-muted">
        Say what the words actually mean here, or why the rule doesn&apos;t apply. Verytas reads the issue again
        with your explanation; if it still can&apos;t tell, the brand team decides.
      </p>
      <textarea id={`dispute-${f.id}`} value={row.dispute} maxLength={2000} aria-describedby={`dispute-help-${f.id}`}
        onChange={(e) => onRow(f.id, { dispute: e.target.value })}
        className="vt-input min-h-16"
        placeholder="e.g. In Marathi, 'भारी' (bhaari) means excellent, not heavy" />
      <div className="flex flex-wrap items-center gap-2">
        <input value={row.language} maxLength={60} onChange={(e) => onRow(f.id, { language: e.target.value })}
          aria-label="Language the words are in (optional)"
          placeholder="Language, if not English" className="vt-input w-44 py-1.5 text-xs" />
        <span className="text-[11px] text-muted" aria-live="polite">
          {left > 0 ? `At least 10 characters (${left} to go)` : onDispute ? "Ready to send." : "Sent with the next re-check, from the bar below."}
        </span>
        <span className="ml-auto flex gap-1.5">
          <button type="button" onClick={() => onRow(f.id, { disputing: false, dispute: "", language: "" })}
            className="vt-btn vt-btn-xs">Cancel</button>
          {onDispute && (
            <button type="button" onClick={send} disabled={sending || left > 0} className="vt-btn vt-btn-xs vt-btn-primary">
              {sending ? "Sending..." : "Send dispute"}
            </button>
          )}
        </span>
      </div>
      {failed && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{failed}</p>}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import { ApiError, relativeTime, withdrawEscalation } from "@/lib/review-client";
import type { EscalationRequest, Finding } from "@/lib/types";
import { REASONS } from "./DecisionControls";

const REASON_LABEL: Record<string, string> = Object.fromEntries(REASONS.map((r) => [r.code, r.label]));
const MIN = 10;

export type EscalateFn = (f: Finding, message: string) => Promise<void>;

/**
 * "A person should look at this." Unlike a dispute, which Prism re-judges, an
 * escalation goes to the brand team's inbox. The message is screened on the way:
 * offers, off-the-record contact and instructions to the AI are refused, and the
 * refusal says what to change.
 */
export function EscalationBox({ f, request, onEscalate, onChanged, side }: {
  f: Finding;
  request: EscalationRequest | undefined;
  onEscalate?: EscalateFn;
  onChanged: () => void;
  side: "creator" | "manager";
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<{ message: string; labels: string[] } | null>(null);

  // A withdrawn request is history: the creator may ask again.
  if (request && request.status !== "withdrawn") {
    const tone = request.status === "open" ? "text-accent" : request.status === "cleared" ? "text-[var(--vt-ok)]"
      : request.status === "upheld" ? "text-[var(--vt-blocker)]" : "text-subtle";
    const state = { open: "With the brand team", cleared: "Cleared by the brand team", upheld: "The finding stands",
      withdrawn: "Withdrawn" }[request.status];
    return (
      <div className="border-t border-line pt-3 text-xs">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={`font-semibold ${tone}`}>{state}</span>
          <span className="text-subtle">
            {side === "manager" && request.raised_by ? `${request.raised_by.name} asked ` : "Asked "}{relativeTime(request.created_at)}
          </span>
        </p>
        <p className="mt-1 text-muted">&ldquo;{request.message}&rdquo;</p>
        {request.resolution && (
          <p className="mt-1.5">
            <span className="font-medium">{request.resolution.by?.name ?? "The brand team"}</span>
            {request.resolution.code ? <span className="text-muted"> · {REASON_LABEL[request.resolution.code] ?? request.resolution.code}</span> : null}
            {request.resolution.note && <span className="block text-muted">&ldquo;{request.resolution.note}&rdquo;</span>}
          </p>
        )}
        {request.status === "open" && side === "creator" && (
          <button type="button" disabled={busy} className="mt-1.5 text-[11px] font-medium text-subtle hover:text-ink"
            onClick={async () => {
              setBusy(true);
              setRefusal(null);
              try {
                await withdrawEscalation(request.id);
                onChanged();
              } catch (err) {
                setRefusal({ message: (err as Error).message, labels: [] });
              } finally {
                setBusy(false);
              }
            }}>
            Withdraw request
          </button>
        )}
        {refusal && request.status === "open" && (
          <p role="alert" className="mt-1.5 text-[11px] text-[var(--vt-blocker)]">{refusal.message}</p>
        )}
        {request.status === "open" && side === "manager" && (
          <Link href={`/escalations?id=${request.id}`} className="mt-1.5 inline-block text-[11px] font-medium text-accent hover:underline">
            Decide in Escalations
          </Link>
        )}
      </div>
    );
  }
  if (!onEscalate) return null;
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="vt-btn vt-btn-quiet self-start py-1.5 text-xs">
        Ask the brand team
      </button>
    );
  }
  const send = async () => {
    setBusy(true);
    setRefusal(null);
    try {
      await onEscalate(f, text.trim());
      setOpen(false);
      setText("");
    } catch (err) {
      const d = err instanceof ApiError ? err.detail as { message?: string; guard?: { label: string }[] } : null;
      if (d?.guard) setRefusal({ message: d.message ?? "This can't be sent.", labels: d.guard.map((g) => g.label) });
      else setRefusal({ message: (err as Error).message, labels: [] });
    } finally {
      setBusy(false);
    }
  };
  const left = MIN - text.trim().length;
  return (
    <div className="vt-pop flex flex-col gap-2 border-t border-line pt-3">
      <label htmlFor={`esc-${f.id}`} className="text-xs font-medium">What should the brand team look at, and why?</label>
      <textarea id={`esc-${f.id}`} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} autoFocus
        placeholder="e.g. The client's brief asks for this line. Is it allowed for their campaign?"
        className="vt-input min-h-16 text-sm" aria-describedby={`esc-${f.id}-note`} />
      {refusal && (
        <div role="alert" className="rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-2 text-xs text-[var(--vt-blocker)]">
          {refusal.message}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" disabled={busy || left > 0} onClick={send} className="vt-btn vt-btn-primary py-1.5 text-xs">
          {busy ? "Sending..." : "Send to the brand team"}
        </button>
        <button type="button" onClick={() => { setOpen(false); setRefusal(null); }} className="vt-btn vt-btn-quiet py-1.5 text-xs">Cancel</button>
        <span id={`esc-${f.id}-note`} className="text-[11px] text-subtle">
          {left > 0 ? `${left} more character${left === 1 ? "" : "s"}` : "A person reviews it by hand. No phone numbers or offers."}
        </span>
      </div>
    </div>
  );
}

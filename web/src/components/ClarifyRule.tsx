"use client";

import { useState } from "react";
import { clarifyRule, updateRule } from "@/lib/review-client";
import type { RuleClarification } from "@/lib/types";
import { shownError } from "@/lib/errors";

/** Draft a clearer wording from the rule's own decided cases; the admin reads, edits, then applies or drops it. */
export function ClarifyRule({ ruleId, code }: { ruleId: number; code: string }) {
  const [draft, setDraft] = useState<RuleClarification | null>(null);
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "drafting" | "applying" | "applied">("idle");
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setState("drafting");
    setError(null);
    try {
      const d = await clarifyRule(ruleId);
      setDraft(d);
      setText(d.proposed.text);
    } catch (e) {
      setError(shownError(e, "Couldn't draft a clearer rule"));
    }
    setState("idle");
  }

  async function apply() {
    if (!draft) return;
    setState("applying");
    setError(null);
    try {
      await updateRule(draft.rule_id, { ...draft.proposed, text: text.trim() });
      setState("applied");
    } catch (e) {
      setError(shownError(e, "Couldn't apply it"));
      setState("idle");
    }
  }

  if (state === "applied") {
    return <p className="mt-3 text-xs font-medium text-[var(--vt-ok)]">Saved as {code} v{(draft?.version ?? 0) + 1}. New reviews use it.</p>;
  }
  if (!draft) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" onClick={start} disabled={state === "drafting"} className="vt-btn vt-btn-quiet vt-btn-sm">
          {state === "drafting" ? "Drafting…" : "Draft a clearer rule"}
        </button>
        {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
      </div>
    );
  }
  const added = (now: string[], before: string[]) => now.filter((e) => !before.includes(e));
  const bad = added(draft.proposed.bad_examples, draft.current.bad_examples);
  const good = added(draft.proposed.good_examples, draft.current.good_examples);
  return (
    <div className="vt-pop mt-3 rounded-lg border border-line bg-surface p-4 text-sm" role="group" aria-label={`Clearer wording for ${code}`}>
      <p className="text-xs text-muted">
        Drafted by <code>{draft.model}</code> from {draft.cases.upheld} upheld, {draft.cases.cleared} dismissed and{" "}
        {draft.cases.unclear} unclear finding{draft.cases.unclear === 1 ? "" : "s"}. Nothing changes until you apply it.
      </p>
      {draft.changes && <p className="mt-2 text-xs leading-5">{draft.changes}</p>}
      <p className="mt-3 text-xs font-medium text-muted">Now</p>
      <p className="mt-0.5 text-muted line-through decoration-1">{draft.current.text}</p>
      <label className="mt-3 block text-xs font-medium text-muted" htmlFor={`clarify-${ruleId}`}>Proposed (you can edit it)</label>
      <textarea id={`clarify-${ruleId}`} value={text} onChange={(e) => setText(e.target.value)} maxLength={1000}
        className="vt-input mt-1 min-h-20" />
      {(bad.length > 0 || good.length > 0) && (
        <ul className="mt-3 flex flex-col gap-1 text-xs">
          {bad.map((e) => <li key={`b${e}`}><span className="font-medium text-[var(--vt-blocker)]">Breaks it:</span> “{e}”</li>)}
          {good.map((e) => <li key={`g${e}`}><span className="font-medium text-[var(--vt-ok)]">Fine:</span> “{e}”</li>)}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button type="button" onClick={apply} disabled={state === "applying" || !text.trim()} className="vt-btn vt-btn-primary">
          {state === "applying" ? "Saving…" : `Apply as ${code} v${draft.version + 1}`}
        </button>
        <button type="button" onClick={() => { setDraft(null); setError(null); }} className="vt-btn vt-btn-quiet">Discard</button>
        {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
      </div>
    </div>
  );
}

"use client";

import { Button, Callout, TextArea } from "@openuidev/react-ui";
import { useMemo, useRef, useState } from "react";
import type { CategoryScore, Finding, Level, ReviewResult } from "@/lib/types";
import { LevelPill, Meter, Panel, SourceBadge } from "./ui";

const LEVEL_ORDER: Level[] = ["blocker", "warning", "advisory"];
// How each coverage status reads on the scorecard. Anything other than "checked" is never shown as a pass.
const COVERAGE_LABEL: Record<string, { text: string; tone: string }> = {
  not_checked: { text: "Not checked", tone: "text-[var(--vt-blocker)]" },
  not_configured: { text: "No rules yet", tone: "text-muted" },
  degraded: { text: "Heuristic only", tone: "text-[var(--vt-warning)]" },
};
const CHANNELS = ["general", "blog", "linkedin", "x", "instagram", "email", "press"] as const;
const REASONS = [
  ["false_positive", "Not actually a problem"],
  ["not_applicable", "Rule doesn't apply here"],
  ["guideline_unclear", "The guideline is unclear"],
  ["intentional", "Intentional, approved exception"],
] as const;

type DecisionState = { action: "accepted" | "rejected"; pending: boolean; error?: string };

export function ReviewWorkspace({ initialBody }: { initialBody: string }) {
  const [title, setTitle] = useState("Launch announcement");
  const [channel, setChannel] = useState<(typeof CHANNELS)[number]>("linkedin");
  const [body, setBody] = useState(initialBody);
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [decisions, setDecisions] = useState<Record<number, DecisionState>>({});
  const cardRefs = useRef(new Map<number, HTMLElement>());

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setDecisions({});
    try {
      const res = await fetch("/api/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, channel, body }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Review failed");
      setResult(json as ReviewResult);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function decide(f: Finding, action: "accepted" | "rejected", reason?: string) {
    setDecisions((d) => ({ ...d, [f.id]: { action, pending: true } }));
    const res = await fetch("/api/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        findingId: f.id,
        action,
        suggestion_id: action === "accepted" ? f.suggestions[0]?.id : undefined,
        reason_code: reason,
      }),
    });
    const json = await res.json().catch(() => ({}));
    setDecisions((d) => ({ ...d, [f.id]: { action, pending: false, error: res.ok ? undefined : json.error } }));
  }

  function focusFinding(id: number) {
    setActive(id);
    cardRefs.current.get(id)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    cardRefs.current.get(id)?.focus({ preventScroll: true });
  }

  const sorted = useMemo(
    () => [...(result?.review.findings ?? [])].sort((a, b) => LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level)),
    [result],
  );
  const summary = result?.review.summary;
  const coverage = result?.review.coverage;

  return (
    <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-5">
        <Panel title="Draft" subtitle="Text under review is treated as data: instructions inside it are ignored">
          <form onSubmit={submit} className="flex flex-col gap-3">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_10rem]">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted">
                Title
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                  maxLength={300}
                  className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium text-muted">
                Channel
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value as (typeof CHANNELS)[number])}
                  className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink"
                >
                  {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>
            <label className="flex flex-col gap-1 text-xs font-medium text-muted">
              Content
              <TextArea value={body} onChange={(e) => setBody(e.target.value)} rows={9} required maxLength={20000} />
            </label>
            <div className="flex items-center gap-3">
              <Button type="submit" variant="primary" disabled={busy || !body.trim()}>
                {busy ? "Checking…" : "Run review"}
              </Button>
              {result && <SourceBadge source={result.source} />}
            </div>
          </form>
        </Panel>

        <div aria-live="polite" className="sr-only">
          {result && `Review complete: ${summary?.blockers ?? 0} blockers, ${summary?.warnings ?? 0} warnings, ${summary?.advisories ?? 0} advisories.`}
        </div>
        {error && <Callout variant="danger" title="Review failed" description={error} />}

        {result && (
          <Panel title="Flagged text" subtitle="Select a highlight to jump to its finding">
            <HighlightedBody body={result.body} findings={sorted} active={active} onSelect={focusFinding} />
          </Panel>
        )}

        {result && summary?.categories && (
          <Panel title="Scorecard" subtitle={`Headline score ${Math.round((summary.overall ?? 0) * 100)}%: the weakest checked category`}>
            <ul className="grid gap-3 sm:grid-cols-2">
              {Object.entries(summary.categories).map(([name, c]) => (
                <li key={name}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="font-medium capitalize">{name}</span>
                    <CoverageTag category={c} />
                  </div>
                  {c.checked && c.score != null && (
                    <Meter value={c.score} label={`${name} score`} tone={c.blockers ? "danger" : c.score >= 0.9 ? "ok" : "accent"} />
                  )}
                </li>
              ))}
            </ul>
            {coverage && (
              <p className="mt-4 border-t border-line pt-3 text-xs text-muted">
                AI disclosure: judged by <code>{coverage.models?.judge}</code>, explanations by{" "}
                <code>{coverage.models?.llm}</code>. {coverage.redactions ?? 0} confidential or personal
                item{coverage.redactions === 1 ? "" : "s"} redacted before any text left Verytas.
                {coverage.not_checked && coverage.not_checked.length > 0 &&
                  ` Not checked this time: ${coverage.not_checked.join(", ")}.`}
              </p>
            )}
          </Panel>
        )}
      </div>

      <div className="flex flex-col gap-3">
        {!result && !busy && (
          <Panel title="Findings">
            <p className="text-sm text-muted">Run a review to see findings here. The sample draft above has a few planted issues.</p>
          </Panel>
        )}
        {busy && <Panel title="Findings"><p className="text-sm text-muted">Checking terminology, claims, tone, accessibility and confidentiality…</p></Panel>}
        {result && sorted.length === 0 && (
          <Callout variant="success" title="No issues found" description="Every check that ran passed." />
        )}
        {sorted.map((f) => (
          <FindingCard
            key={f.id}
            finding={f}
            active={active === f.id}
            decision={decisions[f.id]}
            onDecide={(action, reason) => decide(f, action, reason)}
            refCallback={(el) => {
              if (el) cardRefs.current.set(f.id, el);
              else cardRefs.current.delete(f.id);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function CoverageTag({ category: c }: { category: CategoryScore }) {
  const label = COVERAGE_LABEL[c.status ?? (c.checked ? "checked" : "not_checked")];
  if (!label) return <span className="text-muted">{c.findings} finding{c.findings === 1 ? "" : "s"}</span>;
  return <span className={`font-semibold ${label.tone}`}>{label.text}</span>;
}

function HighlightedBody({ body, findings, active, onSelect }: {
  body: string;
  findings: Finding[];
  active: number | null;
  onSelect: (id: number) => void;
}) {
  // Overlapping spans keep the most severe finding; the others still appear in the list.
  const spans = findings
    .filter((f) => f.span_start != null && f.span_end != null && f.span_end > f.span_start)
    .sort((a, b) => a.span_start! - b.span_start! || LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const f of spans) {
    if (f.span_start! < cursor) continue;
    if (f.span_start! > cursor) parts.push(body.slice(cursor, f.span_start!));
    parts.push(
      <mark
        key={f.id}
        data-level={f.level}
        data-active={active === f.id}
        tabIndex={0}
        role="button"
        aria-label={`${f.level}: ${f.title}`}
        onClick={() => onSelect(f.id)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(f.id))}
      >
        {body.slice(f.span_start!, f.span_end!)}
      </mark>,
    );
    cursor = f.span_end!;
  }
  parts.push(body.slice(cursor));
  return <p className="whitespace-pre-wrap text-sm leading-7">{parts}</p>;
}

function FindingCard({ finding: f, active, decision, onDecide, refCallback }: {
  finding: Finding;
  active: boolean;
  decision?: DecisionState;
  onDecide: (action: "accepted" | "rejected", reason?: string) => void;
  refCallback: (el: HTMLElement | null) => void;
}) {
  const [reason, setReason] = useState<string>("");
  const [rejecting, setRejecting] = useState(false);
  const s = f.suggestions[0];

  return (
    <article
      ref={refCallback}
      tabIndex={-1}
      aria-labelledby={`finding-${f.id}`}
      className={`rounded-xl border bg-surface p-4 transition-shadow ${active ? "border-accent shadow-md" : "border-line"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <LevelPill level={f.level} />
        <span className="text-xs capitalize text-muted">{f.category}</span>
        <span className="text-xs text-muted">· confidence {Math.round(f.confidence * 100)}%</span>
        {f.signature_valid && (
          <span className="ml-auto text-xs text-[var(--vt-ok)]" title="Signed by the agent that produced it; any edit would break the signature">
            ✓ signed
          </span>
        )}
      </div>
      <h3 id={`finding-${f.id}`} className="mt-2 text-sm font-semibold">{f.title}</h3>
      <p className="mt-1 text-sm text-muted">{f.explanation}</p>

      {f.citations.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1">
          {f.citations.map((c) => (
            <li key={`${c.kind}-${c.id}`} className="text-xs">
              <span className="mr-1 rounded bg-bg px-1.5 py-0.5 font-medium uppercase text-muted">{c.kind}</span>
              {c.label}
              {c.source && <span className="text-muted"> · {c.source}</span>}
            </li>
          ))}
        </ul>
      )}

      {s && (
        <div className="mt-3 rounded-lg bg-bg p-3 text-sm">
          <p className="text-xs font-medium text-muted">Suggested minimal edit</p>
          <p className="mt-1">
            <del className="text-[var(--vt-blocker)]">{s.original}</del>
          </p>
          <p>
            <ins className="text-[var(--vt-ok)] no-underline">{s.proposed}</ins>
          </p>
          {s.intent_preserved != null && (
            <p className="mt-1 text-xs text-muted">Meaning preserved: {Math.round(s.intent_preserved * 100)}% likely</p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {decision && !decision.pending && !decision.error ? (
          <p className="text-xs font-medium">
            {decision.action === "accepted" ? "✓ Fix accepted, it will be applied in the next version" : "Dismissed with a reason"}
          </p>
        ) : rejecting ? (
          <>
            <label className="sr-only" htmlFor={`reason-${f.id}`}>Why are you dismissing this?</label>
            <select
              id={`reason-${f.id}`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="rounded-lg border border-line bg-surface px-2 py-1.5 text-xs"
            >
              <option value="">Why dismiss it?</option>
              {REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <Button size="small" variant="secondary" disabled={!reason || decision?.pending} onClick={() => onDecide("rejected", reason)}>
              Dismiss
            </Button>
            <Button size="small" variant="tertiary" onClick={() => setRejecting(false)}>Cancel</Button>
          </>
        ) : (
          <>
            {s && (
              <Button size="small" variant="primary" disabled={decision?.pending} onClick={() => onDecide("accepted")}>
                Accept fix
              </Button>
            )}
            <Button size="small" variant="secondary" disabled={decision?.pending} onClick={() => setRejecting(true)}>
              Dismiss
            </Button>
          </>
        )}
        {decision?.error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{decision.error}</p>}
      </div>
    </article>
  );
}

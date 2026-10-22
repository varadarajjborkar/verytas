"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { aiEdit, ApiError, listDisputes, resubmit, submit, waitForReview } from "@/lib/review-client";
import type { CategoryScore, Dispute, Finding, Level, Review, Source } from "@/lib/types";
import { AgentTree, Sources } from "./review/AgentTree";
import { Checklist, emptyRow, type RowState, sortFindings } from "./review/Checklist";
import { attachmentsPayload, channelOf, Composer, type Draft, emptyDraft } from "./review/Composer";
import { useToast } from "./Toaster";
import { Details, Meter, Panel, SourceBadge } from "./ui";

const LEVEL_ORDER: Level[] = ["blocker", "warning", "advisory"];
// How each coverage status reads on the scorecard. Anything other than "checked" is never shown as a pass.
const COVERAGE_LABEL: Record<string, { text: string; tone: string }> = {
  not_checked: { text: "Not checked", tone: "text-[var(--vt-blocker)]" },
  not_configured: { text: "No rules yet", tone: "text-muted" },
  degraded: { text: "Heuristic only", tone: "text-[var(--vt-warning)]" },
};

type Phase = "idle" | "submitting" | "reviewing" | "done" | "failed";

export function ReviewWorkspace({ initialBody }: { initialBody: string }) {
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(initialBody));
  const [demo, setDemo] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [contentId, setContentId] = useState<number | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [body, setBody] = useState("");
  const [source, setSource] = useState<Source>("live");
  const [round, setRound] = useState(0);
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  // Findings from earlier rounds, so a dispute (filed against an old finding id)
  // can be shown on the matching finding of the new round.
  const [past, setPast] = useState<Record<number, { title: string; key: string }>>({});
  const [active, setActive] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const textRef = useRef<HTMLElement | null>(null);
  const toast = useToast();

  // Live or demo: ask the proxy once, so uploads aren't offered when they can't work.
  useEffect(() => {
    fetch("/api/v/brand-assets").then((r) => setDemo(r.status === 503)).catch(() => setDemo(true));
  }, []);

  async function track(reviewId: number, versionBody: string) {
    setPhase("reviewing");
    setElapsed(0);
    const done = await waitForReview(reviewId, setElapsed);
    setReview(done);
    setBody(versionBody);
    setRows({});
    setPhase(done.status === "done" ? "done" : "failed");
    if (done.status === "failed") {
      setError(done.error ?? "The review failed.");
      toast({ kind: "error", title: "The review failed", detail: done.error ?? "Save a new version to run it again." });
    } else {
      const s = done.summary;
      const total = done.findings.length;
      toast({ kind: s.blockers ? "warning" : "success", title: total ? `Review done: ${total} item${total === 1 ? "" : "s"} to look at` : "Review done: nothing flagged",
        detail: total ? `${s.blockers ?? 0} must fix · ${s.warnings ?? 0} should fix · ${s.advisories ?? 0} to consider` : undefined });
      if (done.coverage?.escalations?.length) toast({ kind: "warning", title: "Escalated to the social media manager",
        detail: done.coverage.escalations[0].reason });
    }
  }

  async function run() {
    setError(null);
    setNotice(null);
    setPhase("submitting");
    let submitted = false;
    try {
      if (demo) {
        const res = await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: draft.title, channel: "linkedin", body: draft.body }) });
        const json = await res.json();
        if (!res.ok) throw new Error(json.error ?? "The demo review failed.");
        setReview(json.review);
        setBody(json.body);
        setSource("demo");
        setPhase("done");
        return;
      }
      const out = await submit({
        title: draft.title, channel: channelOf(draft), tier: draft.tier, body: draft.body,
        attachments: attachmentsPayload(draft),
        creator_notes: {
          intent: draft.intent.trim() || null, language: draft.language.trim() || null,
          ai_used: draft.aiUsed || null, irregularity: draft.irregularityReason.trim() || null,
        },
      });
      submitted = true;
      setContentId(out.content.id);
      setSource("live");
      setRound(1);
      setDisputes([]);
      await track(out.review_id, out.version.body);
    } catch (err) {
      setPhase("failed");
      const message = err instanceof ApiError ? err.message : (err as Error).message;
      setError(message);
      // After a successful submit the content is saved; only following the review failed.
      toast({ kind: "error", title: submitted ? "Lost track of the review" : "Couldn't start the review",
        detail: submitted ? `${message}. The draft is saved; reload to see the result.` : message });
    }
  }

  async function sendBack(newBody?: string) {
    if (!review || !contentId) return;
    const findings = review.findings;
    const payload = {
      body: newBody ?? null,
      apply: findings.filter((f) => rows[f.id]?.apply).map((f) => f.id),
      resolved: findings.filter((f) => rows[f.id]?.done).map((f) => f.id),
      disputes: findings.filter((f) => (rows[f.id]?.dispute ?? "").trim().length >= 10)
        .map((f) => ({ finding_id: f.id, claim: rows[f.id].dispute.trim(), language: rows[f.id].language.trim() || null })),
    };
    setError(null);
    setPhase("submitting");
    let sent = false;
    try {
      setPast((p) => ({ ...p, ...Object.fromEntries(findings.map((f) => [f.id, { title: f.title, key: findingKey(f) }])) }));
      const out = await resubmit(contentId, payload);
      sent = true;
      setRound((r) => r + 1);
      setNotice(["New version saved", out.applied ? `${out.applied} fix${out.applied === 1 ? "" : "es"} applied` : "",
        payload.disputes.length ? `${payload.disputes.length} dispute${payload.disputes.length === 1 ? "" : "s"} sent for re-evaluation` : "",
        ...out.skipped].filter(Boolean).join(" · "));
      if (newBody != null) setDraft((d) => ({ ...d, body: newBody }));
      toast({ kind: "success", title: "Resubmitted", detail: out.applied ? `${out.applied} fix${out.applied === 1 ? "" : "es"} applied; re-checking now` : "Re-checking now" });
      await track(out.submit.review_id, out.submit.version.body);
      const decided = await listDisputes(contentId);
      setDisputes(decided);
      const mine = decided.filter((d) => payload.disputes.some((p) => p.finding_id === d.finding_id));
      if (mine.length) toast({ kind: "info", title: `${mine.length} dispute${mine.length === 1 ? "" : "s"} re-evaluated`,
        detail: mine.map((d) => d.status).join(", ") });
    } catch (err) {
      setPhase("failed");
      setError((err as Error).message);
      toast({ kind: "error", title: sent ? "Lost track of the new review" : "Couldn't resubmit",
        detail: sent ? `${(err as Error).message}. The new version is saved.` : (err as Error).message });
    }
  }

  // Each round writes new finding rows, so disputes (filed on last round's ids)
  // are matched to this round's findings by what was flagged and where.
  const disputeByFinding = useMemo(() => {
    const byKey = new Map(disputes.flatMap((d) => (past[d.finding_id] ? [[past[d.finding_id].key, d] as const] : [])));
    return Object.fromEntries((review?.findings ?? []).flatMap((f) => {
      const d = byKey.get(findingKey(f)) ?? disputes.find((x) => x.finding_id === f.id);
      return d ? [[f.id, d]] : [];
    }));
  }, [disputes, past, review]);
  const sorted = useMemo(() => sortFindings(review?.findings ?? []), [review]);
  const summary = review?.summary;
  const coverage = review?.coverage;
  const escalations = coverage?.escalations ?? [];
  const busy = phase === "submitting" || phase === "reviewing";
  const changes = sorted.filter((f) => rows[f.id]?.apply || rows[f.id]?.done || (rows[f.id]?.dispute ?? "").trim().length >= 10).length;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="flex min-w-0 flex-col gap-5">
        <Panel title="Draft">
          <Composer draft={draft} update={setDraft} onSubmit={run} busy={busy} demo={demo} />
        </Panel>
        {review && contentId && phase === "done" && <AiEditBox contentId={contentId} onUse={(b) => sendBack(b)} />}
      </div>

      <div className="flex min-w-0 flex-col gap-5">
        <div aria-live="polite" className="sr-only">
          {phase === "done" && `Review complete: ${summary?.blockers ?? 0} must fix, ${summary?.warnings ?? 0} should fix, ${summary?.advisories ?? 0} to consider.`}
        </div>
        {error && <p role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}
        {busy && (
          <div className="vt-card flex items-center gap-3 p-5 text-sm text-muted">
            <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            {phase === "reviewing" ? `Checking text, media and context… ${elapsed}s` : "Sending…"}
          </div>
        )}
        {!review && !busy && (
          <div className="vt-card grid min-h-56 place-items-center p-8 text-center">
            <div>
              <p className="text-sm font-medium">Nothing reviewed yet</p>
              <p className="mt-1 text-sm text-muted">Run a review and the issues will appear here, most urgent first.</p>
            </div>
          </div>
        )}

        {review && !busy && (
          <>
            <Panel title={round > 1 ? `To fix · round ${round}` : "To fix"}
              aside={<span className="flex items-center gap-2">
                {summary && <span className="text-xs tabular-nums text-muted">Score {Math.round((summary.overall ?? 0) * 100)}%</span>}
                <SourceBadge source={source} />
              </span>}>
              {notice && <p className="mb-3 rounded-lg bg-sunken px-3 py-2 text-xs text-muted">{notice}</p>}
              {escalations.length > 0 && (
                <div className="mb-3 rounded-xl bg-[var(--vt-warning-bg)] p-3 text-xs" role="status">
                  <p className="font-semibold text-[var(--vt-warning)]">Escalated to the social media manager</p>
                  <ul className="mt-1 list-disc pl-4">{escalations.map((e, i) => <li key={i}>{e.reason}{e.detail ? `: ${e.detail}` : ""}</li>)}</ul>
                </div>
              )}
              {sorted.length === 0 ? (
                <p className="rounded-xl bg-[var(--vt-ok-bg)] px-4 py-3 text-sm font-medium text-[var(--vt-ok)]">All clear. Every check that ran passed.</p>
              ) : (
                <Checklist findings={sorted} rows={rows} disputes={disputeByFinding} active={active}
                  onSelect={(id) => { setActive(id); }}
                  onRow={(id, patch) => setRows((r) => ({ ...r, [id]: { ...(r[id] ?? emptyRow()), ...patch } }))} />
              )}
              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
                <button type="button" disabled={source === "demo" || !contentId || busy} onClick={() => sendBack()}
                  className="vt-btn vt-btn-primary">
                  Resubmit
                </button>
                <span className="text-xs text-muted">{changes ? `${changes} change${changes === 1 ? "" : "s"} selected` : "Re-runs every check"}</span>
              </div>
            </Panel>

            {disputes.length > 0 && (
              <Panel title="Disputes">
                <ul className="flex flex-col gap-2">
                  {disputes.map((d) => (
                    <li key={d.id} className="rounded-xl border border-line bg-raised p-3 text-xs">
                      <p className="font-medium">{past[d.finding_id]?.title ?? `Finding ${d.finding_id}`}</p>
                      <p className="mt-1 text-muted">“{d.claim}”</p>
                      <p className="mt-1"><span className="font-semibold capitalize">{d.status}</span>{d.verdict?.reason ? `: ${d.verdict.reason}` : ""}</p>
                      {d.verdict?.layers && (
                        <p className="mt-1 text-subtle">
                          Reader likelihood: {d.verdict.layers.map((l) => `${l.layer} ${l.p == null ? "n/a" : `${Math.round(l.p * 100)}%`}`).join(", ")}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </Panel>
            )}

            <Panel title="In your draft">
              <HighlightedBody body={body} findings={sorted.filter((f) => (f.source ?? "body") === "body")} active={active}
                onSelect={setActive} innerRef={textRef} />
            </Panel>

            {summary?.categories && (
              <Details summary="Scorecard">
                <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
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
              </Details>
            )}
            {coverage && (
              <Details summary="How it was checked">
                <div className="flex flex-col gap-5">
                  {coverage.agents && coverage.agents.length > 0 && <AgentTree agents={coverage.agents} />}
                  {coverage.sources && coverage.sources.length > 1 && <Sources sources={coverage.sources} />}
                  <p className="text-xs leading-5 text-muted">
                    Judged by <code>{coverage.models?.judge}</code>, written by <code>{coverage.models?.llm}</code>
                    {coverage.models?.vision && <>, images seen by <code>{coverage.models.vision}</code></>}.
                    {" "}{coverage.redactions ?? 0} confidential item{coverage.redactions === 1 ? "" : "s"} redacted before leaving Verytas.
                    {coverage.not_checked && coverage.not_checked.length > 0 && ` Not checked: ${coverage.not_checked.join(", ")}.`}
                  </p>
                </div>
              </Details>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AiEditBox({ contentId, onUse }: { contentId: number; onUse: (body: string) => void }) {
  const toast = useToast();
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<{ body: string; changes: string[]; remaining: string[]; model: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      setProposal(await aiEdit(contentId, instruction));
      toast({ kind: "success", title: "Rewrite ready" });
    } catch (err) {
      setError((err as Error).message);
      toast({ kind: "error", title: "Couldn't rewrite", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Details summary="Edit with AI">
      <div className="flex flex-col gap-3">
        <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={2000}
          placeholder="e.g. Make it warmer and drop the competitor jab"
          className="vt-input min-h-20" />
        <button type="button" disabled={busy || instruction.trim().length < 3} onClick={ask} className="vt-btn vt-btn-quiet self-start">
          {busy ? "Rewriting…" : "Suggest a rewrite"}
        </button>
        {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
        {proposal && (
          <div className="vt-pop flex flex-col gap-3 rounded-xl border border-line bg-raised p-3">
            <p className="whitespace-pre-wrap text-sm leading-6">{proposal.body}</p>
            {proposal.changes.length > 0 && (
              <ul className="list-disc pl-4 text-xs text-muted">{proposal.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
            )}
            {proposal.remaining.length > 0 && (
              <p className="text-xs text-[var(--vt-warning)]">Still flagged: {proposal.remaining.join("; ")}</p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => onUse(proposal.body)} className="vt-btn vt-btn-primary">
                Use this and re-check
              </button>
              <span className="text-xs text-subtle">Written by {proposal.model}</span>
            </div>
          </div>
        )}
      </div>
    </Details>
  );
}

function CoverageTag({ category: c }: { category: CategoryScore }) {
  const label = COVERAGE_LABEL[c.status ?? (c.checked ? "checked" : "not_checked")];
  if (!label) return <span className="text-muted">{c.findings} finding{c.findings === 1 ? "" : "s"}</span>;
  return <span className={`font-semibold ${label.tone}`}>{label.text}</span>;
}

/** Maps a code point offset to a UTF-16 index in `text`. */
function utf16Index(text: string): (cp: number) => number {
  const starts: number[] = [];
  let i = 0;
  for (const ch of text) {
    starts.push(i);
    i += ch.length;
  }
  starts.push(i);
  return (cp) => starts[Math.min(Math.max(cp, 0), starts.length - 1)];
}

function findingKey(f: Finding): string {
  return `${f.category}|${f.source ?? "body"}|${f.quote ?? f.title}`;
}

function HighlightedBody({ body, findings, active, onSelect, innerRef }: {
  body: string;
  findings: Finding[];
  active: number | null;
  onSelect: (id: number) => void;
  innerRef: React.RefObject<HTMLElement | null>;
}) {
  // The API counts characters in code points; JS strings index UTF-16 units,
  // so every emoji before a span would shift it by one. Convert first.
  const at = utf16Index(body);
  findings = findings.map((f) => f.span_start == null || f.span_end == null ? f
    : { ...f, span_start: at(f.span_start), span_end: at(f.span_end) });
  // Overlapping spans keep the most severe finding; the others still appear in the checklist.
  const spans = findings
    .filter((f) => f.span_start != null && f.span_end != null && f.span_end > f.span_start)
    .sort((a, b) => a.span_start! - b.span_start! || LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const f of spans) {
    if (f.span_start! < cursor) continue;
    if (f.span_start! > cursor) parts.push(body.slice(cursor, f.span_start!));
    parts.push(
      <mark key={f.id} data-level={f.level} data-active={active === f.id} tabIndex={0} role="button"
        aria-label={`${f.level}: ${f.title}`} onClick={() => onSelect(f.id)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(f.id))}>
        {body.slice(f.span_start!, f.span_end!)}
      </mark>,
    );
    cursor = f.span_end!;
  }
  parts.push(body.slice(cursor));
  return <p ref={innerRef as React.RefObject<HTMLParagraphElement>} className="whitespace-pre-wrap text-sm leading-7">{parts}</p>;
}

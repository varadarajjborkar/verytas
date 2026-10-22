"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { journey } from "@/lib/journey";
import {
  ApiError, decide as decideFinding, FINISHED, getContent, getReview, getTimeline, listDisputes, listPeople, nextSteps,
  relativeTime, resubmit, STATUS_LABEL, transition, waitForReview,
} from "@/lib/review-client";
import { canDecide, sideOf } from "@/lib/roles";
import type { ContentDetail, ContentStatus, Dispute, Person, Review, Timeline } from "@/lib/types";
import { JourneyMap } from "../Journey";
import { useToast } from "../Toaster";
import { Details, Meter, tabKeys } from "../ui";
import { Activity } from "./Activity";
import { AgentTree, Sources } from "./AgentTree";
import { Checklist, emptyRow, type RowState, sortFindings } from "./Checklist";
import type { DecideFn } from "./DecisionControls";
import { AiEditBox, CoverageTag, findingKey, HighlightedBody } from "./parts";
import { VersionCompare } from "./VersionCompare";

type Phase = "loading" | "checking" | "ready" | "failed" | "missing";

const STATUS_TONE: Record<ContentStatus, string> = {
  draft: "bg-sunken text-muted",
  in_review: "bg-[var(--vt-advisory-bg)] text-[var(--vt-advisory)]",
  changes_requested: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
  approved: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
  published: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
  withdrawn: "bg-sunken text-subtle",
};

/**
 * One piece of content, opened from the history: where it is on its way to
 * published, the text with every issue marked in place, the issues and the
 * shared activity beside it, and the next step in its workflow.
 *
 * The creator edits, applies fixes, disputes and re-checks. The brand team
 * reads the same piece but decides instead: confirm, dismiss or escalate each
 * finding, then approve or send it back with a note.
 */
export function ReviewView({ contentId, role, userId, onChanged }: {
  contentId: number; role: string; userId: number | null; onChanged: () => void;
}) {
  const [content, setContent] = useState<ContentDetail | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  // Findings from earlier rounds, so a dispute (filed against an old finding id)
  // can be shown on the matching finding of the new round.
  const [past, setPast] = useState<Record<number, { title: string; key: string }>>({});
  const [active, setActive] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [busy, setBusy] = useState(false);
  const [override, setOverride] = useState<{ to: ContentStatus; message: string } | null>(null);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const [announce, setAnnounce] = useState("");
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [people, setPeople] = useState<Map<number, Person>>(new Map());
  const [pane, setPane] = useState<"issues" | "activity">("issues");
  const [docView, setDocView] = useState<"text" | "compare">("text");
  const [sendingBack, setSendingBack] = useState(false);
  const textRef = useRef<HTMLElement | null>(null);
  const live = useRef(contentId);
  // Stops polling a review nobody is looking at any more.
  const polling = useRef<AbortController | null>(null);
  const decidedSeen = useRef(new Set<number>());
  const toast = useToast();

  const loadTimeline = useCallback(() => {
    getTimeline(contentId).then((t) => { if (live.current === contentId) setTimeline(t); }).catch(() => {});
  }, [contentId]);
  useEffect(() => {
    loadTimeline();
    listPeople().then((ps) => setPeople(new Map(ps.map((p) => [p.id, p])))).catch(() => {});
  }, [loadTimeline]);

  // Starts with a request, not a state change: on mount the initial state is already "loading",
  // and a re-check resets it itself before calling this.
  const load = useCallback(async () => {
    live.current = contentId;
    polling.current?.abort();
    const poll = new AbortController();
    polling.current = poll;
    let waited = false;
    try {
      const detail = await getContent(contentId);
      if (live.current !== contentId) return;
      setContent(detail);
      if (detail.latest_review_id == null) {
        setReview(null);
        setPhase("ready");
        return;
      }
      setPhase("checking");
      const done = await waitForReview(detail.latest_review_id, (s) => {
        waited = true;
        if (live.current === contentId) setElapsed(s);
      }, poll.signal);
      if (live.current !== contentId) return;
      setReview(done);
      setRows({});
      if (waited) loadTimeline();
      setPhase(done.status === "failed" ? "failed" : "ready");
      if (done.status === "failed") setError(done.error ?? "The review failed. Re-check to run it again.");
      else if (waited) {
        // Only a review that finished while the person watched is news; one opened already done is not.
        const n = done.findings.length;
        const blockers = done.summary?.blockers ?? 0;
        const message = n === 0 ? "Review finished: all clear" : `Review finished: ${n} issue${n === 1 ? "" : "s"}${blockers ? `, ${blockers} must fix` : ""}`;
        setAnnounce(message);
        toast({ kind: blockers ? "warning" : "success", title: message });
        const escalated = done.coverage?.escalations?.length ?? 0;
        if (escalated) toast({ kind: "warning", title: "Escalated to the social media manager", detail: done.coverage?.escalations?.[0]?.reason });
      }
      const found = await listDisputes(contentId).catch(() => []);
      if (live.current !== contentId) return;
      setDisputes(found);
      const fresh = found.filter((d) => d.status !== "queued" && d.status !== "running" && !decidedSeen.current.has(d.id));
      fresh.forEach((d) => decidedSeen.current.add(d.id));
      const decided = fresh.length;
      if (waited && decided) toast({ kind: "info", title: `${decided} dispute${decided === 1 ? "" : "s"} decided`, detail: "See Disputes for the reasons." });
    } catch (err) {
      if (live.current !== contentId || poll.signal.aborted) return;
      const status = err instanceof ApiError ? err.status : 0;
      setPhase(status === 404 ? "missing" : "failed");
      setError((err as Error).message);
    }
  // toast is stable for the app's lifetime.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentId, loadTimeline]);

  // The shell keys this view by content id, so another review mounts fresh; only the load runs here.
  useEffect(() => {
    // load() awaits the request before any state change; the rule can't see through async functions.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    return () => {
      live.current = -1;
      polling.current?.abort();
    };
  }, [load]);

  // Selecting an issue brings its highlight into view.
  useEffect(() => {
    if (active == null) return;
    textRef.current?.querySelector(`mark[data-id="${active}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [active]);

  const latest = content?.versions.at(-1);
  const body = latest?.body ?? "";
  const status = content?.status ?? "draft";
  const readOnly = status === "published" || status === "withdrawn";
  const findings = useMemo(() => sortFindings(review?.findings ?? []), [review]);
  const disputeByFinding = useMemo(() => {
    const byKey = new Map(disputes.flatMap((d) => (past[d.finding_id] ? [[past[d.finding_id].key, d] as const] : [])));
    return Object.fromEntries(findings.flatMap((f) => {
      const d = byKey.get(findingKey(f)) ?? disputes.find((x) => x.finding_id === f.id);
      return d ? [[f.id, d]] : [];
    }));
  }, [disputes, past, findings]);
  const changes = findings.filter((f) => rows[f.id]?.apply || rows[f.id]?.done
    || (rows[f.id]?.dispute ?? "").trim().length >= 10).length;

  async function recheck(newBody?: string) {
    if (!review && newBody == null) return;
    const all = review?.findings ?? [];
    const payload = {
      body: newBody ?? null,
      apply: all.filter((f) => rows[f.id]?.apply).map((f) => f.id),
      resolved: all.filter((f) => rows[f.id]?.done).map((f) => f.id),
      disputes: all.filter((f) => (rows[f.id]?.dispute ?? "").trim().length >= 10)
        .map((f) => ({ finding_id: f.id, claim: rows[f.id].dispute.trim(), language: rows[f.id].language.trim() || null })),
    };
    setBusy(true);
    setError(null);
    try {
      setPast((p) => ({ ...p, ...Object.fromEntries(all.map((f) => [f.id, { title: f.title, key: findingKey(f) }])) }));
      const out = await resubmit(contentId, payload);
      setEditing(false);
      setNotice([`Version ${out.submit.version.version_no} saved`,
        out.applied ? `${out.applied} fix${out.applied === 1 ? "" : "es"} applied` : "",
        payload.disputes.length ? `${payload.disputes.length} dispute${payload.disputes.length === 1 ? "" : "s"} sent` : "",
        ...out.skipped].filter(Boolean).join(" · "));
      toast({ kind: "success", title: "Re-checking" });
      onChanged();
      // The old round's findings point into the old text; drop them before the new text shows.
      setReview(null);
      setActive(null);
      setRows({});
      setElapsed(0);
      setPhase("loading");
      await load();
      loadTimeline();
      onChanged();
    } catch (err) {
      setError((err as Error).message);
      toast({ kind: "error", title: "Couldn't re-check", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  async function move(to: ContentStatus, note?: string, force = false) {
    setBusy(true);
    try {
      const out = await transition(contentId, to, note, force);
      setContent((c) => (c ? { ...c, status: out.status } : c));
      setOverride(null);
      setSendingBack(false);
      loadTimeline();
      toast({ kind: "success", title: STATUS_LABEL[out.status] });
      onChanged();
    } catch (err) {
      const message = (err as Error).message;
      // Approval with open blockers needs a written reason; offer that instead of a dead end.
      if (err instanceof ApiError && err.status === 409 && /override/i.test(message)) setOverride({ to, message });
      else toast({ kind: "error", title: "Couldn't change the status", detail: message });
    } finally {
      setBusy(false);
    }
  }

  // A decision changes the finding (its history) and the timeline; reload both, not the whole review.
  const decide: DecideFn = async (f, action, reasonCode, reasonText) => {
    try {
      await decideFinding(f.id, action, reasonCode, reasonText);
      if (review) {
        const fresh = await getReview(review.id);
        if (live.current === contentId) setReview(fresh);
      }
      loadTimeline();
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't record the decision", detail: (err as Error).message });
      throw err;
    }
  };

  if (phase === "missing") {
    return <div className="vt-card p-8 text-center text-sm text-muted">This review no longer exists, or you can&apos;t see it.</div>;
  }
  if (!content) {
    return (
      <div aria-busy="true" className="flex animate-pulse flex-col gap-4">
        <div className="h-20 rounded-[14px] bg-sunken" />
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <div className="h-80 rounded-[14px] bg-sunken" /><div className="h-80 rounded-[14px] bg-sunken" />
        </div>
      </div>
    );
  }

  const summary = review?.summary;
  const coverage = review?.coverage;
  const escalations = coverage?.escalations ?? [];
  const checking = phase === "checking" || phase === "loading";
  const steps = nextSteps(status, role, userId != null && content.created_by === userId);
  const manager = sideOf(role) === "manager";
  const author = userId != null && content.created_by === userId;
  // The creator's tools (edit, apply fixes, dispute, re-check) belong to the author.
  const creatorTools = !manager || author;
  const route = timeline ? journey(timeline) : null;
  const versions = content.versions;
  // New text after approval needs a fresh decision; the API moves it back to review.
  const demotes = status === "approved";

  return (
    <div className="flex flex-col gap-5">
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      {/* Header: what this is, where it stands, what to do next. */}
      <header className="vt-card flex flex-col gap-4 p-4 md:flex-row md:items-center md:p-5">
        <div className="min-w-0 flex-1">
          <h2 className={`truncate text-lg font-semibold tracking-tight ${FINISHED.includes(status) ? "text-muted" : ""}`}>{content.title}</h2>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted">
            <span className={`rounded-md px-1.5 py-0.5 font-medium ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>
            <span className="capitalize">{content.channel.replace("_", " ")}</span>
            <span aria-hidden>·</span>
            <span>Version {latest?.version_no ?? 1}</span>
            <span aria-hidden>·</span>
            <span>{relativeTime(latest?.created_at ?? content.created_at)}</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {summary?.overall != null && !checking && (
            <span className="mr-2 text-right">
              <span className="block text-[11px] text-subtle">Score</span>
              <span className="text-lg font-semibold tabular-nums">{Math.round(summary.overall * 100)}%</span>
            </span>
          )}
          {!readOnly && !editing && creatorTools && (
            <button type="button" disabled={busy || checking} className="vt-btn vt-btn-quiet"
              onClick={() => { setEditText(body); setEditing(true); }}>
              Edit text
            </button>
          )}
          {steps.filter((s) => s.to !== "withdrawn").map((s) => (
            <button key={s.to} type="button" disabled={busy || checking}
              onClick={() => (s.to === "changes_requested" ? setSendingBack(true) : move(s.to))}
              className={`vt-btn ${s.primary ? "vt-btn-primary" : "vt-btn-quiet"}`}>
              {s.label}
            </button>
          ))}
          {steps.some((s) => s.to === "withdrawn") && (confirmWithdraw ? (
            <span className="vt-pop flex items-center gap-1.5 rounded-xl bg-[var(--vt-blocker-bg)] py-1 pl-3 pr-1 text-xs">
              <span className="font-medium text-[var(--vt-blocker)]">Withdraw for good?</span>
              <button type="button" disabled={busy} onClick={() => { setConfirmWithdraw(false); void move("withdrawn"); }}
                className="vt-btn px-2 py-1 text-xs text-[var(--vt-blocker)]">Withdraw</button>
              <button type="button" onClick={() => setConfirmWithdraw(false)} className="vt-btn vt-btn-quiet px-2 py-1 text-xs">Keep</button>
            </span>
          ) : (
            <button type="button" disabled={busy} onClick={() => setConfirmWithdraw(true)}
              className="vt-btn px-2 text-xs text-subtle hover:text-[var(--vt-blocker)]">
              Withdraw
            </button>
          ))}
        </div>
      </header>

      {route && <JourneyMap journey={route} status={status} />}
      {sendingBack && (
        <SendBackBox busy={busy} onCancel={() => setSendingBack(false)} onConfirm={(note) => move("changes_requested", note)} />
      )}
      {override && (
        <OverrideBox message={override.message} busy={busy} onCancel={() => setOverride(null)}
          onConfirm={(note) => move(override.to, note, true)} />
      )}
      {error && <p role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}
      {notice && <p className="rounded-xl bg-sunken px-4 py-2.5 text-xs text-muted">{notice}</p>}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_25rem]">
        {/* The text, with every issue marked where it is. */}
        <section className="vt-card min-w-0 p-5 md:p-7" aria-label={manager && !author ? "The text" : "Your text"}>
          {versions.length > 1 && !editing && (
            <div role="tablist" aria-label="Show" className="mb-5 inline-flex rounded-lg bg-sunken p-0.5 text-xs font-medium"
              onKeyDown={tabKeys(["text", "compare"] as const, docView, setDocView, `doc-${contentId}`)}>
              {([["text", `Version ${latest?.version_no ?? 1}`], ["compare", "Compare versions"]] as const).map(([k, l]) => (
                <button key={k} id={`doc-${contentId}-${k}`} type="button" role="tab" aria-selected={docView === k}
                  aria-controls={`doc-${contentId}-panel`} tabIndex={docView === k ? 0 : -1} onClick={() => setDocView(k)}
                  className={`rounded-md px-3 py-1.5 transition ${docView === k ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
                  {l}
                </button>
              ))}
            </div>
          )}
          {checking && (
            <div className="mb-5 flex items-center gap-3 rounded-xl bg-sunken px-4 py-3 text-sm text-muted" role="status">
              <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              Checking text, media and context… {elapsed}s
            </div>
          )}
          <div id={`doc-${contentId}-panel`} role={versions.length > 1 && !editing ? "tabpanel" : undefined}
            aria-labelledby={versions.length > 1 && !editing ? `doc-${contentId}-${docView}` : undefined}>
          {editing ? (
            <div className="flex flex-col gap-3">
              <textarea value={editText} onChange={(e) => setEditText(e.target.value)} maxLength={100000} autoFocus
                aria-label="Edit the text" className="vt-input min-h-80 resize-y text-[15px] leading-7" />
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={busy || !editText.trim() || editText === body}
                  onClick={() => recheck(editText)} className="vt-btn vt-btn-primary">
                  {busy ? "Saving…" : "Save and re-check"}
                </button>
                <button type="button" onClick={() => setEditing(false)} className="vt-btn vt-btn-quiet">Cancel</button>
                <span className="text-xs text-subtle">
                  {demotes ? "This is approved: new text goes back for approval." : "Fixes ticked on the right are applied too."}
                </span>
              </div>
            </div>
          ) : docView === "compare" && versions.length > 1 ? (
            <VersionCompare versions={versions} />
          ) : (
            <HighlightedBody body={body} findings={findings.filter((f) => (f.source ?? "body") === "body")}
              active={active} onSelect={setActive} innerRef={textRef} />
          )}
          </div>
          {coverage?.sources && coverage.sources.length > 1 && !editing && (
            <p className="mt-6 border-t border-line pt-4 text-xs text-subtle">
              Also read: {coverage.sources.filter((s) => s.id !== "body").map((s) => s.id).join(", ")}
            </p>
          )}
        </section>

        {/* What to fix, most urgent first. */}
        <aside className="flex min-w-0 flex-col gap-5 xl:sticky xl:top-6" aria-label="Issues">
          <section className="vt-card p-4">
            <div role="tablist" aria-label="Side panel" className="mb-3 flex gap-4 border-b border-line text-sm"
              onKeyDown={tabKeys(["issues", "activity"] as const, pane, setPane, `pane-${contentId}`)}>
              {([["issues", "Issues", findings.length], ["activity", "Activity", route ? route.comments + route.decisions : null]] as const)
                .map(([k, l, n]) => (
                  <button key={k} id={`pane-${contentId}-${k}`} type="button" role="tab" aria-selected={pane === k}
                    aria-controls={`pane-${contentId}-panel`} tabIndex={pane === k ? 0 : -1} onClick={() => setPane(k)}
                    className={`-mb-px border-b-2 pb-2 font-semibold transition ${pane === k ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}>
                    {l}{n ? <span className="ml-1.5 text-xs font-medium tabular-nums text-subtle">{n}</span> : null}
                  </button>
                ))}
            </div>
            <div id={`pane-${contentId}-panel`} role="tabpanel" aria-labelledby={`pane-${contentId}-${pane}`}>
            {pane === "activity" ? (
              <Activity timeline={timeline} contentId={contentId} versionId={latest?.id ?? null} onPosted={loadTimeline} />
            ) : <>
            {escalations.length > 0 && (
              <div className="mb-3 rounded-xl bg-[var(--vt-warning-bg)] p-3 text-xs" role="status">
                <p className="font-semibold text-[var(--vt-warning)]">Escalated to the social media manager</p>
                <ul className="mt-1 list-disc pl-4">{escalations.map((e, i) => <li key={i}>{e.reason}{e.detail ? `: ${e.detail}` : ""}</li>)}</ul>
              </div>
            )}
            {checking ? (
              <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded-lg bg-sunken" />)}</div>
            ) : !review ? (
              <p className="text-sm text-muted">Not reviewed yet.</p>
            ) : findings.length === 0 ? (
              <p className="rounded-xl bg-[var(--vt-ok-bg)] px-4 py-3 text-sm font-medium text-[var(--vt-ok)]">All clear. Every check that ran passed.</p>
            ) : (
              <Checklist findings={findings} rows={rows} disputes={disputeByFinding} active={active} onSelect={setActive}
                onRow={(id, patch) => setRows((r) => ({ ...r, [id]: { ...(r[id] ?? emptyRow()), ...patch } }))}
                creator={creatorTools} people={people}
                decide={manager && canDecide(role) && !readOnly ? decide : undefined}
                canDismissBlockers={role === "approver" || role === "brand_admin"} />
            )}
            {!readOnly && review && !checking && creatorTools && (
              <div className="mt-4 flex items-center gap-3 border-t border-line pt-4">
                <button type="button" disabled={busy} onClick={() => recheck()} className="vt-btn vt-btn-primary">
                  {changes ? `Apply ${changes} and re-check` : "Re-check"}
                </button>
                <span className="text-xs text-subtle">
                  {demotes ? "Goes back for approval" : changes ? "Makes a new version" : "Runs every check again"}
                </span>
              </div>
            )}
            </>}
            </div>
          </section>

          {disputes.length > 0 && (
            <Details summary={`Disputes (${disputes.length})`}>
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
            </Details>
          )}
          {!readOnly && review && !checking && creatorTools && <AiEditBox contentId={contentId} onUse={(b) => recheck(b)} />}
          {summary?.categories && !checking && (
            <Details summary="Scorecard">
              <ul className="grid gap-x-6 gap-y-3">
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
          {coverage && !checking && (
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
        </aside>
      </div>
    </div>
  );
}

/** Sending a piece back: the note is what the creator reads first, on the map and in the feed. */
function SendBackBox({ busy, onCancel, onConfirm }: { busy: boolean; onCancel: () => void; onConfirm: (note: string) => void }) {
  const [note, setNote] = useState("");
  return (
    <div className="vt-pop vt-card p-4" role="group" aria-label="Request changes">
      <p className="text-sm font-medium">What should the creator change?</p>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} autoFocus
        placeholder="e.g. Drop the 40% claim until legal signs off, and use our product name spelling."
        aria-label="Note for the creator" className="vt-input mt-3 min-h-16" />
      <div className="mt-3 flex items-center gap-2">
        <button type="button" disabled={busy || !note.trim()} onClick={() => onConfirm(note.trim())} className="vt-btn vt-btn-primary">Send back</button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet">Cancel</button>
        <span className="text-xs text-muted">Required. The creator sees it on the piece and on their home page.</span>
      </div>
    </div>
  );
}

/** Approving over open blockers or unchecked parts needs a written reason, kept in the audit log. */
function OverrideBox({ message, busy, onCancel, onConfirm }: {
  message: string; busy: boolean; onCancel: () => void; onConfirm: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  return (
    <div className="vt-pop rounded-xl bg-[var(--vt-warning-bg)] p-4" role="alert">
      <p className="text-sm font-medium text-[var(--vt-warning)]">{message}</p>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="Why it's fine to go ahead"
        aria-label="Reason for overriding" className="vt-input mt-3 min-h-16" />
      <div className="mt-3 flex items-center gap-2">
        <button type="button" disabled={busy || note.trim().length < 10} onClick={() => onConfirm(note.trim())}
          className="vt-btn vt-btn-primary">Override and continue</button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet">Cancel</button>
        <span className="text-xs text-muted">At least 10 characters. It is recorded in the audit log.</span>
      </div>
    </div>
  );
}

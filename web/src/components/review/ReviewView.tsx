"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { journey } from "@/lib/journey";
import {
  ApiError, decide as decideFinding, escalate, FINISHED, getContent, getReview, getTimeline, listComments, listDisputes,
  listEscalations, listPeople, nextSteps,
  relativeTime, resubmit, STATUS_HINT, STATUS_LABEL, transition, waitForReview, whereLabel,
} from "@/lib/review-client";
import { canDecide, sideOf } from "@/lib/roles";
import type { ContentDetail, ContentStatus, Dispute, EscalationRequest, Finding, Person, PinnedComment, Review, SecondLooks, Timeline } from "@/lib/types";
import { JourneyMap } from "../Journey";
import { useModalFocus } from "../Drawer";
import { CheckIcon, CloseIcon, HistoryIcon } from "../Icons";
import { useToast } from "../Toaster";
import { SummarizeButton } from "../assist/SummarizeButton";
import { Details, Meter, tabKeys } from "../ui";
import { Activity } from "./Activity";
import { AgentTree, Sources } from "./AgentTree";
import { Attachments } from "./Attachments";
import { DocumentPages } from "./DocumentPages";
import { Checklist, emptyRow, rowCall, type RowState, sortFindings } from "./Checklist";
import { callOf, type DecideFn } from "./DecisionControls";
import { AiEditBox, CleanResult, CoverageTag, findingKey, HighlightedBody } from "./parts";
import { VersionCompare } from "./VersionCompare";
import { channelName } from "@/lib/channels";
import { AiInfoButton } from "../AiInfo";

type Phase = "loading" | "checking" | "ready" | "failed" | "missing";

const STATUS_TONE: Record<ContentStatus, string> = {
  draft: "bg-sunken text-muted",
  in_review: "bg-[var(--vt-advisory-bg)] text-[var(--vt-advisory)]",
  changes_requested: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
  approved: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
  published: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
  withdrawn: "bg-sunken text-subtle",
};
const fixOf = (f: Finding) => ((f.source ?? "body") === "body" ? f.suggestions[0] : undefined);

/**
 * One piece of content, opened from the history: the piece itself on a raised sheet with every issue marked in
 * place, the issues as a list beside it that open where they are, and one floating bar that says how much is
 * left and what to do next.
 *
 * The creator picks fixes, ticks issues off, disputes and re-checks; the fixes they pick show in the text at
 * once. The brand team reads the same piece but decides instead: ask for the change, keep the words with a
 * reason, or escalate, then approve or send it back. A change they ask for shows in the text too, so the
 * sheet always reads as the piece would go out.
 */
export function ReviewView({ contentId, role, userId, onChanged, onNext }: {
  contentId: number; role: string; userId: number | null; onChanged: () => void;
  /** The next piece in the queue, offered once this one is sent on. */
  onNext?: () => void;
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
  // Comments pinned to a moment of a video or drawn on an image, shown where they point.
  const [pins, setPins] = useState<PinnedComment[]>([]);
  const [people, setPeople] = useState<Map<number, Person>>(new Map());
  const [history, setHistory] = useState(false);
  const [show, setShow] = useState<"all" | "open">("all");
  const [docView, setDocView] = useState<"text" | "compare">("text");
  const [sendingBack, setSendingBack] = useState(false);
  // Walking means each decision opens the next open issue; picking a row by hand stops it.
  const [walking, setWalking] = useState(false);
  const [leaving, setLeaving] = useState<number | null>(null);
  const [sent, setSent] = useState<{ to: ContentStatus; changes: number } | null>(null);
  const [requests, setRequests] = useState<Record<number, EscalationRequest>>({});
  const textRef = useRef<HTMLElement | null>(null);
  const live = useRef(contentId);
  // Stops polling a review nobody is looking at any more.
  const polling = useRef<AbortController | null>(null);
  const decidedSeen = useRef(new Set<number>());
  const toast = useToast();

  const loadTimeline = useCallback(() => {
    getTimeline(contentId).then((t) => { if (live.current === contentId) setTimeline(t); }).catch(() => {});
    listComments(contentId).then((c) => { if (live.current === contentId) setPins(c); }).catch(() => {});
    // The latest request per finding: a withdrawn one may be followed by a new ask.
    listEscalations("all", contentId).then((rows) => {
      if (live.current !== contentId) return;
      const by: Record<number, EscalationRequest> = {};
      for (const r of [...rows].sort((a, b) => a.id - b.id)) by[r.finding.id] = r;
      setRequests(by);
    }).catch(() => {});
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
      // Open the most urgent issue, so its explanation, source and fix are the first thing on screen.
      setActive(sortFindings(done.findings)[0]?.id ?? null);
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

  // Selecting an issue brings its words into view.
  useEffect(() => {
    if (active == null) return;
    textRef.current?.querySelector(`[data-id="${active}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
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

  const manager = sideOf(role) === "manager";
  const author = userId != null && content?.created_by === userId;
  // The creator's tools (edit, apply fixes, dispute, re-check) belong to the author.
  const creatorTools = !manager || author;
  const deciding = manager && canDecide(role) && !readOnly;
  // A brand team member reading their own piece has both sets of tools; their decisions are what count.
  const creatorCalls = creatorTools && !deciding;
  const calls = useMemo(() => new Map(findings.map((f) => [f.id, rowCall(f, rows[f.id], creatorCalls)])), [findings, rows, creatorCalls]);
  // Someone who can act on the rows walks the ones still open; anyone else simply reads them in turn.
  const acting = (creatorTools && !readOnly) || deciding;
  const open = acting ? findings.filter((f) => !calls.get(f.id)) : findings;
  // "Open" filters only while some issues are decided and some are not; otherwise every issue shows.
  const filterable = open.length > 0 && open.length < findings.length;
  const asked = findings.filter((f) => callOf(f) === "asked");
  const blocking = findings.filter((f) => f.level === "blocker" && callOf(f) !== "kept").length;

  // The text reads as it would go out: a fix the creator picked, or a change the brand team asked for, sits in
  // place of the flagged words.
  const replaced = useMemo(() => Object.fromEntries(findings.flatMap((f) => {
    const s = fixOf(f);
    const on = (creatorTools && rows[f.id]?.apply) || (deciding && callOf(f) === "asked");
    return s && on ? [[f.id, { original: s.original, proposed: s.proposed }]] : [];
  })), [findings, rows, creatorTools, deciding]);
  const kept = useMemo(() => new Set(findings.filter((f) => {
    const c = calls.get(f.id)?.state;
    return c === "kept" || c === "done";
  }).map((f) => f.id)), [findings, calls]);

  // The next open issue after the given one, wrapping round; null once nothing is left.
  const nextOpen = useCallback((after: number | null, skip?: number) => {
    const left = open.filter((f) => f.id !== skip);
    if (!left.length) return null;
    const at = after == null ? -1 : findings.findIndex((f) => f.id === after);
    return (left.find((f) => findings.indexOf(f) > at) ?? left[0]).id;
  }, [open, findings]);
  const step = useCallback((dir: 1 | -1) => {
    if (!findings.length) return;
    const at = active == null ? (dir === 1 ? -1 : findings.length) : findings.findIndex((f) => f.id === active);
    setActive(findings[(at + dir + findings.length) % findings.length].id);
  }, [findings, active]);
  const walk = useCallback(() => {
    const target = active != null && open.some((f) => f.id === active) && !walking ? active : nextOpen(active);
    if (target == null) return;
    setWalking(true);
    setActive(target);
  }, [active, open, walking, nextOpen]);
  // Stable, so the document pages' memoised parts re-render only when their own issue is picked.
  const pick = useCallback((id: number | null) => { setWalking(false); setActive(id); }, []);
  // Read at the end of a save round trip, after the person may have stopped walking or opened another row.
  const walkingNow = useRef(walking);
  useEffect(() => { walkingNow.current = walking; }, [walking]);

  // Number keys jump to an issue, J and K step through them, Enter makes the open one's main call.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Runs in the capture phase, before a modal's own Escape closes it, so a key meant for the modal stays there.
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey || document.querySelector("[aria-modal='true']")) return;
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (/^[1-9]$/.test(e.key) && findings[+e.key - 1]) { pick(findings[+e.key - 1].id); return; }
      if (e.key === "j" || e.key === "J") { e.preventDefault(); if (acting) walk(); else step(1); return; }
      if (e.key === "k" || e.key === "K") { e.preventDefault(); step(-1); return; }
      if (e.key === "Escape" && active != null) { pick(null); return; }
      // Only with nothing focused: a focused highlight or button handles Enter itself.
      if (e.key === "Enter" && active != null && t === document.body) {
        const main = document.querySelector<HTMLButtonElement>(`[data-finding="${active}"] [data-primary-call]`);
        if (main && !main.disabled) { e.preventDefault(); main.click(); }
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

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
      setWalking(false);
      setRows({});
      setElapsed(0);
      setPhase("loading");
      setSent(null);
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
      setSent({ to: out.status, changes: asked.length });
      setActive(null);
      setWalking(false);
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
  // While walking, a call made opens the next open issue; the one just decided no longer counts as open.
  // Moves on only if the row just decided is still the open one: a row picked meanwhile wins.
  const advance = (id: number) => {
    if (!walkingNow.current) return;
    const n = nextOpen(id, id);
    setActive((cur) => (cur === id ? n : cur));
    if (n == null) setWalking(false);
  };
  const decided = (f: Finding) => advance(f.id);
  const onRow = (id: number, patch: Partial<RowState>) => {
    setRows((r) => ({ ...r, [id]: { ...(r[id] ?? emptyRow()), ...patch } }));
    if (patch.apply || patch.done) advance(id);
  };

  if (phase === "missing") {
    return <div className="vt-card p-8 text-center text-sm text-muted">This review no longer exists, or you can&apos;t see it.</div>;
  }
  if (!content) {
    return (
      <div aria-busy="true" className="flex animate-pulse flex-col gap-4">
        <div className="h-14 rounded-[14px] bg-sunken" />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <div className="h-96 rounded-[22px] bg-sunken" /><div className="h-80 rounded-[14px] bg-sunken" />
        </div>
      </div>
    );
  }

  const summary = review?.summary;
  const coverage = review?.coverage;
  const escalations = coverage?.escalations ?? [];
  const checking = phase === "checking" || phase === "loading";
  const steps = nextSteps(status, role, author);
  const route = timeline ? journey(timeline) : null;
  const versions = content.versions;
  // New text after approval needs a fresh decision; the API moves it back to review.
  const demotes = status === "approved";
  const writer = people.get(content.created_by);
  const writerFirst = writer?.name.split(" ")[0] ?? "the creator";
  const activityCount = route ? route.comments + route.decisions : 0;

  return (
    <div className="flex flex-col gap-5 pb-28">
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      {/* Header: what this is and where it stands; what to do next lives in the bar at the bottom. */}
      <header className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="min-w-0 flex-1">
          <h2 title={content.title} className={`line-clamp-2 break-words text-lg font-semibold tracking-tight ${FINISHED.includes(status) ? "text-muted" : ""}`}>{content.title}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted">
            <span title={STATUS_HINT[status]} className={`rounded-md px-1.5 py-0.5 font-medium ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>
            <span>{channelName(content.channel)}</span>
            <span aria-hidden>·</span>
            <span>Version {latest?.version_no ?? 1}</span>
            {summary?.overall != null && !checking && <><span aria-hidden>·</span><span className="tabular-nums" title="The score of the weakest check on this version. 100% means no check found anything.">Score {Math.round(summary.overall * 100)}%</span></>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button type="button" onClick={() => setHistory(true)} className="vt-btn vt-btn-quiet vt-btn-sm">
            <HistoryIcon size={14} />History{activityCount > 0 && <span className="tabular-nums text-subtle">{activityCount}</span>}
          </button>
          {/* The brand team's brief and item chat; the button renders nothing for creators and auditors. */}
          {manager && <SummarizeButton kind="content" id={contentId} title={content.title} />}
          {!readOnly && !editing && creatorTools && (
            <button type="button" disabled={busy || checking} className="vt-btn vt-btn-quiet vt-btn-sm"
              onClick={() => { setEditText(body); setEditing(true); }}>
              Edit text
            </button>
          )}
          {/* Every move stays one click away here; the bar below offers the one that fits what was decided. */}
          {steps.filter((s) => s.to !== "withdrawn").map((s) => (
            <button key={s.to} type="button" disabled={busy || checking}
              onClick={() => (s.to === "changes_requested" ? setSendingBack(true) : move(s.to))}
              className="vt-btn vt-btn-quiet vt-btn-sm">
              {s.label}
            </button>
          ))}
          {steps.some((s) => s.to === "withdrawn") && (confirmWithdraw ? (
            <span className="vt-pop flex items-center gap-1.5 rounded-xl bg-[var(--vt-blocker-bg)] py-1 pl-3 pr-1 text-xs">
              <span className="font-medium text-[var(--vt-blocker)]">Withdraw for good?</span>
              <button type="button" disabled={busy} onClick={() => { setConfirmWithdraw(false); void move("withdrawn"); }}
                className="vt-btn vt-btn-xs text-[var(--vt-blocker)]">Withdraw</button>
              <button type="button" onClick={() => setConfirmWithdraw(false)} className="vt-btn vt-btn-quiet vt-btn-xs">Keep</button>
            </span>
          ) : (
            <button type="button" disabled={busy} onClick={() => setConfirmWithdraw(true)}
              className="vt-btn vt-btn-xs text-subtle hover:text-[var(--vt-blocker)]">
              Withdraw
            </button>
          ))}
        </div>
      </header>

      {override && (
        <OverrideBox message={override.message} busy={busy} onCancel={() => setOverride(null)}
          onConfirm={(note) => move(override.to, note, true)} />
      )}
      {error && <p role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}
      {notice && <p className="rounded-xl bg-sunken px-4 py-2.5 text-xs text-muted">{notice}</p>}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="flex min-w-0 flex-col gap-5">
          {/* The piece itself, with every issue marked where it is. */}
          <article className="vt-paper min-w-0 p-5 md:px-8 md:py-7" aria-label={manager && !author ? "The piece" : "Your piece"}>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#1a5fd1] to-[#4c9bff] text-xs font-semibold text-white">
                {(writer?.name ?? "?").slice(0, 1).toUpperCase()}
              </span>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block text-sm font-semibold">{author ? "You" : writer?.name ?? "Creator"}</span>
                <span className="text-xs text-muted">Version {latest?.version_no ?? 1} · {relativeTime(latest?.created_at ?? content.created_at)}</span>
              </span>
              {versions.length > 1 && !editing && (
                <div role="tablist" aria-label="Show" className="inline-flex rounded-lg bg-sunken p-0.5 text-xs font-medium"
                  onKeyDown={tabKeys(["text", "compare"] as const, docView, setDocView, `doc-${contentId}`)}>
                  {([["text", "This version"], ["compare", "Compare versions"]] as const).map(([k, l]) => (
                    <button key={k} id={`doc-${contentId}-${k}`} type="button" role="tab" aria-selected={docView === k}
                      aria-controls={`doc-${contentId}-panel`} tabIndex={docView === k ? 0 : -1} onClick={() => setDocView(k)}
                      className={`rounded-md px-3 py-1.5 transition ${docView === k ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
                      {l}
                    </button>
                  ))}
                </div>
              )}
            </div>
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
                    {demotes ? "This is approved: new text goes back for approval." : "Fixes you picked are applied too."}
                  </span>
                </div>
              </div>
            ) : docView === "compare" && versions.length > 1 ? (
              <VersionCompare versions={versions} />
            ) : (
              <HighlightedBody body={body} findings={findings.filter((f) => (f.source ?? "body") === "body")}
                active={active} onSelect={pick} innerRef={textRef} replaced={replaced} kept={kept} leaving={leaving} />
            )}
            </div>
            {latest && !editing && docView === "text" && (
              <>
                {/* Keyed by version: a drawing or a selected stretch belongs to the version it was made on. */}
                <Attachments key={`media-${latest.id}`} contentId={contentId} version={latest} findings={findings} active={active} onSelect={pick}
                  comments={pins} onPinned={loadTimeline} canComment={role !== "brand_admin"} />
                {coverage?.sources && <DocumentPages key={latest.id} contentId={contentId} version={latest} sources={coverage.sources}
                  findings={findings} active={active} onSelect={pick} kept={kept} />}
              </>
            )}
          </article>
          {route && <JourneyMap journey={route} status={status} />}
        </div>

        {/* The issues, most urgent first; each opens where it is. Pinned beside a long piece. */}
        <aside className="flex min-w-0 flex-col gap-4 xl:sticky xl:top-[4.5rem] xl:max-h-[calc(100dvh-6rem)] xl:overflow-y-auto xl:pb-24"
          aria-label="Issues">
          <div className="flex items-baseline gap-2 px-1">
            <h3 className="text-sm font-semibold">Issues</h3>
            {!checking && review && findings.length > 0 && (
              <span className="text-xs tabular-nums text-subtle">
                {acting ? `${findings.length - open.length} of ${findings.length} ${creatorTools ? "handled" : "decided"}` : findings.length}
              </span>
            )}
            {/* Only while it would change the list: with nothing decided, or everything, both views are the same. */}
            {acting && !checking && filterable && (
              <div role="group" aria-label="Show issues" className="ml-auto flex gap-0.5">
                {(["all", "open"] as const).map((k) => (
                  <button key={k} type="button" aria-pressed={show === k} onClick={() => setShow(k)}
                    className={`rounded-md px-2 py-0.5 text-xs transition ${show === k ? "bg-sunken text-ink" : "text-muted hover:text-ink"}`}>
                    {k === "all" ? "All" : <>Open <span className="tabular-nums text-subtle">{open.length}</span></>}
                  </button>
                ))}
              </div>
            )}
          </div>
          {escalations.length > 0 && (
            <div className="rounded-xl bg-[var(--vt-warning-bg)] p-3 text-xs" role="status">
              <p className="font-semibold text-[var(--vt-warning)]">Escalated to the social media manager</p>
              <ul className="mt-1 list-disc pl-4">{escalations.map((e, i) => <li key={i}>{e.reason}{e.detail ? `: ${e.detail}` : ""}</li>)}</ul>
            </div>
          )}
          {checking ? (
            <div className="flex flex-col gap-1.5">
              <CheckingNote />
              {[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-2xl bg-sunken" />)}
            </div>
          ) : !review ? (
            <p className="px-1 text-sm text-muted">Not reviewed yet.</p>
          ) : findings.length === 0 ? (
            // A failed check has its own alert above; only a finished one can say what was checked.
            review.status === "done" ? <CleanResult categories={summary?.categories} /> : null
          ) : (
            <Checklist findings={findings} rows={rows} disputes={disputeByFinding} active={active} onSelect={pick} show={filterable ? show : "all"}
              onRow={onRow} creator={creatorTools} people={people} escalations={requests} onEscalationChanged={loadTimeline}
              onEscalate={creatorTools && !readOnly ? async (f, message) => {
                await escalate(f.id, message);
                toast({ kind: "success", title: "Sent to the brand team", detail: "A person will review it by hand." });
                loadTimeline();
                onChanged();
              } : undefined}
              decide={deciding ? decide : undefined} onBusy={setLeaving} onDecided={decided} creatorCalls={creatorCalls}
              canDismissBlockers={role === "approver" || role === "brand_admin"} />
          )}
          <p className="px-1 text-[11px] text-subtle">
            AI-assisted review: people make the final call.{" "}
            <AiInfoButton className="underline underline-offset-2 hover:text-ink" />
          </p>

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
                {coverage.second_looks && <SecondLookList looks={coverage.second_looks} />}
                <p className="text-xs leading-5 text-muted">
                  Judged by <code>{coverage.models?.judge}</code>
                  {coverage.models?.second_judge && <> (must rules also by <code>{coverage.models.second_judge}</code>)</>}, written by <code>{coverage.models?.llm}</code>
                  {coverage.models?.vision && <>, images seen by <code>{coverage.models.vision}</code></>}.
                  {" "}{coverage.redactions ?? 0} confidential item{coverage.redactions === 1 ? "" : "s"} redacted before leaving Verytas.
                  {(coverage.research?.searched.length ?? 0) > 0 && ` Searched the web for ${coverage.research!.searched.length} unsupported claim${coverage.research!.searched.length === 1 ? "" : "s"} (${coverage.research!.searched.map((s) => s.outcome).join("; ")}).`}
                  {(coverage.precedents?.attached ?? 0) > 0 && ` ${coverage.precedents!.attached} finding${coverage.precedents!.attached === 1 ? "" : "s"} shown what reviewers decided before on similar words.`}
                  {coverage.not_checked && coverage.not_checked.length > 0 && ` Not checked: ${coverage.not_checked.join(", ")}.`}
                </p>
              </div>
            </Details>
          )}
        </aside>
      </div>

      <Dock>
        {sent ? (
          <>
            <span className="flex items-center gap-1.5 whitespace-nowrap text-[13px]">
              <CheckIcon size={14} className="text-[var(--vt-ok)]" />
              <b className="font-semibold">{STATUS_LABEL[sent.to]}</b>
              {sent.to === "changes_requested" && sent.changes > 0 && <span className="text-muted">{writerFirst} gets {sent.changes} change{sent.changes === 1 ? "" : "s"}</span>}
            </span>
            {onNext ? <button type="button" onClick={onNext} className="vt-btn vt-btn-primary rounded-full">Next piece →</button>
              : <button type="button" onClick={() => setSent(null)} className="vt-btn vt-btn-quiet rounded-full">Close</button>}
          </>
        ) : checking ? (
          <span className="flex items-center gap-2.5 whitespace-nowrap py-1.5 pr-3 text-[13px] text-muted" role="status">
            <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            Checking… {elapsed}s
          </span>
        ) : review ? (
          <DockBody findings={findings} calls={calls} active={active} open={open.length} acting={acting} walking={walking}
            onWalk={walk} busy={busy}
            also={creatorTools && !readOnly && changes > 0 ? { label: `Apply ${changes} and re-check`, run: () => recheck() } : null}
            message={!acting ? <><b className="font-semibold">{findings.length} issue{findings.length === 1 ? "" : "s"}</b></>
              : open.length ? <><b className="font-semibold">{open.length} to go</b>{deciding && <span className="hidden text-muted sm:inline">{blocking ? `${blocking} block${blocking === 1 ? "s" : ""} approval` : "none block approval"}</span>}</>
              : creatorTools ? <><b className="font-semibold">{findings.length ? "All handled" : "All clear"}</b>{changes > 0 && <span className="hidden text-muted sm:inline">{changes} to apply</span>}</>
              : <><b className="font-semibold">All decided</b><span className="hidden text-muted sm:inline">{asked.length ? `${asked.length} change${asked.length === 1 ? "" : "s"} for ${writerFirst}` : "nothing stands"}</span></>}
            done={readOnly ? null : creatorTools ? (
              changes > 0 ? { label: `Apply ${changes} and re-check`, run: () => recheck() }
                : steps.find((s) => s.primary && s.to === "in_review") ? { label: "Send for approval", run: () => move("in_review") }
                : findings.length ? { label: "Re-check", run: () => recheck() } : null
            ) : deciding ? (
              asked.length && steps.some((s) => s.to === "changes_requested") ? { label: `Send back with ${asked.length}`, run: () => setSendingBack(true) }
                : steps.find((s) => s.primary) ? { label: steps.find((s) => s.primary)!.label, run: () => move(steps.find((s) => s.primary)!.to), ready: blocking === 0 }
                : steps.some((s) => s.to === "changes_requested") ? { label: "Send back", run: () => setSendingBack(true) } : null
            ) : null} />
        ) : null}
      </Dock>
      {sendingBack && (
        <SendBackSheet asked={asked} to={writerFirst} busy={busy} onCancel={() => setSendingBack(false)}
          onSend={(note) => move("changes_requested", note)} />
      )}
      {history && (
        <HistoryPanel onClose={() => setHistory(false)}>
          <Activity timeline={timeline} contentId={contentId} versionId={latest?.id ?? null} onPosted={loadTimeline} />
        </HistoryPanel>
      )}
    </div>
  );
}

// Portalled to the body: the app's glass panels blur what is behind them, which pins a fixed child to the panel
// instead of the window.
function Dock({ children }: { children: React.ReactNode }) {
  if (!children || typeof document === "undefined") return null;
  return createPortal(<div className="vt-dock" role="region" aria-label="Review progress">{children}</div>, document.body);
}

type Done = { label: string; run: () => void; ready?: boolean } | null;
type Calls = Map<number, ReturnType<typeof rowCall>>;

/** While a check runs: what it is doing and how long it takes, so nobody wonders whether to press again.
 * The elapsed time is already beside the title and in the bar below. */
function CheckingNote() {
  return (
    <p className="px-1 pb-1 text-sm text-muted">
      Checking against the brand&apos;s rules and approved facts. Text takes a few seconds, images and video
      longer; you can leave this page and come back.
    </p>
  );
}

/** Dots for every issue, how many are left, and one button: walk the open ones, or the move that fits what was decided. */
function DockBody({ findings, calls, active, open, acting, walking, onWalk, message, done, busy, also }: {
  findings: Finding[]; calls: Calls; active: number | null; open: number; acting: boolean; walking: boolean;
  onWalk: () => void; message: React.ReactNode; done: Done; busy: boolean;
  /** A move that can't wait for the rest: fixes already chosen, applied while other issues are still open. */
  also?: { label: string; run: () => void } | null;
}) {
  const left = acting ? open > 0 : findings.length > 0;
  return (
    <>
      {findings.length > 0 && <PipChain findings={findings} calls={calls} active={active} />}
      <span className="flex min-w-0 items-baseline gap-1.5 whitespace-nowrap text-[13px]">{message}</span>
      {also && open > 0 && (
        <button type="button" disabled={busy} onClick={also.run} className="vt-btn h-9 rounded-full px-4 font-semibold">
          {also.label}
        </button>
      )}
      {left && (!done || open > 0) ? (
        <button type="button" onClick={onWalk} className="vt-btn vt-btn-primary h-9 rounded-full px-4 font-semibold">
          {walking || !acting ? "Next issue" : open < findings.length ? "Continue" : "Walk me through"}
          <kbd className="rounded border border-current px-1 text-[10px] font-medium opacity-60">J</kbd>
        </button>
      ) : done ? (
        <button type="button" disabled={busy} onClick={done.run}
          className={`vt-btn h-9 rounded-full px-4 font-semibold ${done.ready ? "border-transparent bg-[var(--vt-ok)] text-white" : "vt-btn-primary"}`}>
          {done.label}
        </button>
      ) : null}
    </>
  );
}

const PIP_STEP = 14; // a pip's 9px and the 5px gap after it
const PIP_WINDOW = 9; // pips in view at once; the rest of the chain fades out at either end

/**
 * One dot per issue, as a chain that keeps the issue in hand in the middle: a few either side are in view and
 * the rest fade out at both ends, so a long review reads as calmly as a short one. Deciding slides the chain on
 * to the next. Short chains show whole and stay put.
 */
function PipChain({ findings, calls, active }: { findings: Finding[]; calls: Calls; active: number | null }) {
  const states = findings.map((f) => {
    const c = calls.get(f.id)?.state;
    return !c ? undefined : c === "kept" || c === "done" ? "kept" : "asked";
  });
  const pips = findings.map((f, i) => (
    <i key={f.id} className="vt-pip shrink-0" data-level={f.level} data-state={states[i]} data-on={f.id === active && !states[i]} />
  ));
  if (findings.length <= PIP_WINDOW) return <span className="hidden gap-[5px] sm:flex" aria-hidden>{pips}</span>;
  // In hand: the issue open in the list, else the next undecided one, else (all decided) the last.
  const at = findings.findIndex((f) => f.id === active);
  const next = states.findIndex((s) => !s);
  const focus = at >= 0 ? at : next >= 0 ? next : findings.length - 1;
  const width = PIP_WINDOW * PIP_STEP - 5;
  return (
    <span className="vt-pip-window hidden sm:block" style={{ width }} aria-hidden>
      <span className="vt-pip-track" style={{ transform: `translateX(${width / 2 - (focus * PIP_STEP + 4.5)}px)` }}>{pips}</span>
    </span>
  );
}

/** Sending a piece back: what goes back, as asked, and an optional word for the creator. */
function SendBackSheet({ asked, to, busy, onCancel, onSend }: {
  asked: Finding[]; to: string; busy: boolean; onCancel: () => void; onSend: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  useModalFocus(panel, onCancel);
  // The creator reads the note first (on the map and in the feed), so it carries the list as well as any words.
  const list = asked.map((f) => {
    const s = fixOf(f);
    return s ? `${f.title}: ${s.proposed ? `use "${s.proposed}"` : `remove "${s.original}"`}` : f.title;
  });
  const compose = () => {
    const lines = list.length ? `Changes asked: ${list.join("; ")}.` : "";
    return [note.trim(), lines].filter(Boolean).join(" ").slice(0, 2000);
  };
  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-40">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_35%,transparent)]" onClick={onCancel} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-label="Send back"
        className="vt-pop absolute bottom-[5.5rem] left-1/2 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 rounded-[20px] border border-line-strong bg-raised p-4 shadow-[var(--vt-shadow-pop)]">
        <h3 className="mb-2.5 text-sm font-semibold">Going back to {to}</h3>
        {asked.length > 0 ? (
          <ol className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
            {asked.map((f) => {
              const s = fixOf(f);
              return (
                <li key={f.id} className="flex items-baseline gap-2 text-[13px]">
                  <i aria-hidden className="h-1.5 w-1.5 shrink-0 -translate-y-px rounded-full bg-[var(--vt-ok)]" />
                  <span>{f.title}{s && <span className="block text-muted">{s.proposed ? <>Use “{s.proposed}”</> : <>Remove “{s.original}”</>}</span>}</span>
                </li>
              );
            })}
          </ol>
        ) : <p className="text-[13px] text-muted">No issue was asked to change. Say what to change in the note.</p>}
        <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1500} data-autofocus
          placeholder={`Add a note for ${to}${asked.length ? " (optional)" : ""}`} aria-label={`Note for ${to}`}
          className="vt-input mt-3 min-h-16 text-[13px]" />
        <div className="mt-3 flex justify-end gap-1.5">
          <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet vt-btn-sm">Cancel</button>
          <button type="button" disabled={busy || (!asked.length && !note.trim())} onClick={() => onSend(compose())}
            className="vt-btn vt-btn-primary vt-btn-sm">Send back</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/** The piece's journey and conversation, slid in from the right so the piece stays where it is. */
function HistoryPanel({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  useModalFocus(panel, onClose);
  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-40">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[4px]" onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-label="History"
        className="vt-pop absolute inset-y-3 right-3 flex w-[min(26rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h3 className="text-sm font-semibold">History</h3>
          <button type="button" onClick={onClose} aria-label="Close history" className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-sunken"><CloseIcon size={15} /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

const LOOK_OUTCOME: Record<SecondLooks["asked"][number]["outcome"], string> = {
  flagged: "raised a finding", cleared: "cleared it", "confirmed flag": "agreed it breaks the rule",
  "confirmed clear": "agreed it is fine", unavailable: "could not answer; the first answer stands",
};

/** Must-rule questions answered by both judges: the first answer, the larger model's, and what changed. */
function SecondLookList({ looks }: { looks: SecondLooks }) {
  if (!looks.asked.length && !looks.unasked) return null;
  return (
    <div className="flex flex-col gap-1.5 text-xs">
      <p className="text-muted">
        Second looks by <code>{looks.model}</code>: questions on must rules also go to the larger judge, and its answer decides.
        {looks.unasked > 0 && <span className="font-medium text-[var(--vt-warning)]"> {looks.unasked} paragraph{looks.unasked === 1 ? " was" : "s were"} left to the first judge (budget reached).</span>}
      </p>
      <ul className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-3">
        {looks.asked.map((l, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-x-2">
            <code className="font-medium">{l.rule}</code>
            <span className="text-muted">{whereLabel({ source: l.source })}, {l.unit}</span>
            <span className="tabular-nums">{Math.round(l.first * 100)}%{l.second != null && <> → {Math.round(l.second * 100)}%</>}</span>
            <span className="text-muted">{LOOK_OUTCOME[l.outcome]}</span>
          </li>
        ))}
      </ul>
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

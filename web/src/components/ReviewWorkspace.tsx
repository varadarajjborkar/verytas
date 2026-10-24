"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useStored, writeStored } from "@/lib/stored";
import { ApiError, listContents, submit } from "@/lib/review-client";
import type { ContentRow, Review } from "@/lib/types";
import { BackButton } from "./BackButton";
import { Drawer } from "./Drawer";
import { HistoryIcon, PanelIcon, PlusIcon } from "./Icons";
import { Checklist, emptyRow, type RowState, sortFindings } from "./review/Checklist";
import { attachmentsPayload, channelOf, Composer, type Draft, emptyDraft } from "./review/Composer";
import { HighlightedBody } from "./review/parts";
import { ReviewHistory } from "./review/ReviewHistory";
import { ReviewQueue } from "./review/ReviewQueue";
import { ReviewView } from "./review/ReviewView";
import { useToast } from "./Toaster";
import { useViewer } from "./Viewer";

/**
 * The review workspace: a history of every piece on the left (like a chat
 * list), and on the right either a focused "new review" form or one opened
 * review. The open review lives in the URL (?id=), so links and Back work.
 * The new-review form stays mounted while a review is open, so a half-written
 * draft survives a look at an older piece.
 *
 * This is the creator's workspace. The brand team gets the review queue
 * instead (review/ReviewQueue.tsx): a different page for a different job.
 */
const RAIL_KEY = "vt-review-rail";
const NARROW = "(max-width: 1599px)";
function onWidth(cb: () => void) {
  const q = window.matchMedia(NARROW);
  q.addEventListener("change", cb);
  return () => q.removeEventListener("change", cb);
}

export function ReviewWorkspace({ initialBody }: { initialBody: string }) {
  const { side, loading, demo } = useViewer();
  if (loading) return <div aria-busy="true" aria-label="Loading" className="h-96 animate-pulse rounded-[14px] bg-sunken" />;
  // Without an API there is no queue to work, so everyone gets the sample review form.
  // The sample caption suits the demo's sample brand only; a real workspace starts with an empty box.
  return side === "manager" && !demo ? <ReviewQueue /> : <CreatorWorkspace initialBody={demo ? initialBody : ""} />;
}

function CreatorWorkspace({ initialBody }: { initialBody: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const selected = Number(params.get("id")) || null;
  const { me, loading: viewerLoading } = useViewer();
  const [rows, setRows] = useState<ContentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [demo, setDemo] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  // Four columns (sidebar, this list, the piece, its issues) squeeze the piece on a laptop screen, so with a
  // piece open below 1600px the list starts folded. Opening or folding it by hand is remembered and wins.
  const railChoice = useStored(RAIL_KEY);
  const narrow = useSyncExternalStore(onWidth, () => window.matchMedia(NARROW).matches, () => false);
  const collapsed = railChoice ? railChoice === "closed" : selected != null && narrow;
  const setCollapsed = (fold: boolean) => writeStored(RAIL_KEY, fold ? "closed" : "open");
  // Only the newest request may write the list, so a slow reply can't overwrite a newer one.
  const seq = useRef(0);

  const refresh = useCallback(() => {
    const ticket = ++seq.current;
    return listContents(true)
      .then((r) => { if (ticket === seq.current) setRows(r); })
      .catch((err) => { if (err instanceof ApiError && err.status === 503) setDemo(true); })
      .finally(() => { if (ticket === seq.current) setLoading(false); });
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  // Keep the list fresh while anything in it is still being checked: one request
  // at a time, and none while the tab is in the background.
  const pending = rows.some((r) => r.latest_review && (r.latest_review.status === "queued" || r.latest_review.status === "running"));
  useEffect(() => {
    if (!pending) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (!document.hidden) await refresh();
      if (!stop) timer = setTimeout(tick, 4000);
    };
    timer = setTimeout(tick, 4000);
    return () => { stop = true; clearTimeout(timer); };
  }, [pending, refresh]);

  const go = (id: number | null) => {
    setRailOpen(false);
    router.push(id == null ? pathname : `${pathname}?id=${id}`, { scroll: false });
  };

  const rail = (collapsible: boolean) => (
    <ReviewHistory rows={rows} loading={loading} selected={selected} scopes={[]} scope="mine" demo={demo}
      onScope={() => {}} onSelect={(id) => go(id)} onNew={() => go(null)} homeLabel={{ text: "New review", icon: "plus" }}
      onCollapse={collapsible ? () => setCollapsed(true) : undefined} />
  );
  const showing = selected != null && !demo;

  return (
    <div className={`grid items-start gap-5 ${collapsed ? "lg:grid-cols-[3.25rem_minmax(0,1fr)]" : "lg:grid-cols-[17rem_minmax(0,1fr)]"}`}>
      {collapsed ? (
        <div className="vt-card hidden flex-col items-center gap-1.5 py-2.5 lg:sticky lg:top-[4.5rem] lg:flex">
          <button type="button" onClick={() => setCollapsed(false)} aria-label="Show reviews" title="Show reviews"
            className="grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
            <PanelIcon size={16} />
          </button>
          <button type="button" onClick={() => go(null)} aria-label="New review" title="New review"
            className="grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
            <PlusIcon size={16} />
          </button>
        </div>
      ) : (
        <aside className="vt-card vt-rail hidden overflow-hidden lg:sticky lg:top-[4.5rem] lg:block lg:h-[calc(100dvh-10.5rem)]">{rail(true)}</aside>
      )}
      <div className="flex gap-2 lg:hidden">
        <button type="button" onClick={() => setRailOpen(true)} className="vt-btn vt-btn-quiet"><HistoryIcon size={15} /> Reviews</button>
        {selected != null && <button type="button" onClick={() => go(null)} className="vt-btn vt-btn-quiet"><PlusIcon size={15} /> New</button>}
      </div>
      {railOpen && <div className="lg:hidden"><Drawer label="Reviews" onClose={() => setRailOpen(false)}>{rail(false)}</Drawer></div>}

      <div className="min-w-0">
        {/* Held until the viewer is known: mounting as a guessed role would offer the wrong tools. */}
        {/* The same way out as the brand team's queue has, floating along once the page scrolls past it. */}
        {showing && !viewerLoading && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center"><BackButton onClick={() => go(null)} label="My reviews" /></div>
            <ReviewView key={selected} contentId={selected} role={me?.role ?? "creator"} userId={me?.id ?? null} onChanged={refresh} />
          </div>
        )}
        <div hidden={showing}>
          <NewReview initialBody={initialBody} demo={demo} onCreated={(id) => { void refresh(); go(id); }} />
        </div>
      </div>
    </div>
  );
}

/** A focused form for one new piece. On submit the review opens on its own page. */
function NewReview({ initialBody, demo, onCreated }: { initialBody: string; demo: boolean; onCreated: (id: number) => void }) {
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(initialBody));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoResult, setDemoResult] = useState<{ review: Review; body: string } | null>(null);
  const toast = useToast();

  async function run() {
    setBusy(true);
    setError(null);
    try {
      if (demo) {
        const res = await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: draft.title, channel: "linkedin", body: draft.body }) });
        const json = await res.json();
        if (!res.ok) throw new Error(json.error ?? "The demo review failed.");
        setDemoResult({ review: json.review, body: json.body });
        return;
      }
      const out = await submit({
        title: draft.title, channel: channelOf(draft), tier: draft.tier, body: draft.body, event_id: draft.eventId,
        attachments: attachmentsPayload(draft),
        creator_notes: {
          intent: draft.intent.trim() || null, language: draft.language.trim() || null,
          ai_used: draft.aiUsed || null, irregularity: draft.irregularityReason.trim() || null,
          brief: draft.brief.trim() || null, brief_audio_blob_id: draft.briefAudio?.id ?? null,
        },
      });
      toast({ kind: "success", title: "Review started" });
      setDraft(emptyDraft(""));
      onCreated(out.content.id);
    } catch (err) {
      const message = (err as Error).message;
      setError(message);
      toast({ kind: "error", title: "Couldn't start the review", detail: message });
    } finally {
      setBusy(false);
    }
  }

  if (demoResult) return <DemoResult {...demoResult} onBack={() => setDemoResult(null)} />;
  return (
    <section className="vt-card mx-auto w-full max-w-3xl p-5 md:p-8" aria-label="New review">
      <h2 className="text-lg font-semibold tracking-tight">New review</h2>
      <p className="mb-6 mt-1 text-sm text-muted">Paste the text as it will be posted, add any images, documents or video, and run it.</p>
      {error && <p role="alert" className="mb-4 rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}
      <Composer draft={draft} update={setDraft} onSubmit={run} busy={busy} demo={demo} />
    </section>
  );
}

/** Demo mode has nowhere to save a review, so the sample result is shown in place, read-only. */
function DemoResult({ review, body, onBack }: { review: Review; body: string; onBack: () => void }) {
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [active, setActive] = useState<number | null>(null);
  const findings = useMemo(() => sortFindings(review.findings), [review]);
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">Sample result: connect the Verytas API to save reviews.</p>
        <button type="button" onClick={onBack} className="vt-btn vt-btn-quiet">Back to the form</button>
      </div>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_25rem]">
        <section className="vt-card p-5 md:p-7">
          <HighlightedBody body={body} findings={findings.filter((f) => (f.source ?? "body") === "body")} active={active}
            onSelect={setActive} innerRef={{ current: null }} />
        </section>
        <section className="vt-card p-4">
          <h3 className="mb-3 text-sm font-semibold">Issues</h3>
          <Checklist findings={findings} rows={rows} disputes={{}} active={active} onSelect={setActive}
            onRow={(id, patch) => setRows((r) => ({ ...r, [id]: { ...(r[id] ?? emptyRow()), ...patch } }))} />
        </section>
      </div>
    </div>
  );
}

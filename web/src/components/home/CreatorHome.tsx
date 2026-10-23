"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getTimeline, listContents, relativeTime, STATUS_LABEL } from "@/lib/review-client";
import type { ContentRow, Person, TimelineItem } from "@/lib/types";
import { ArrowRightIcon, ChatIcon, PlusIcon } from "../Icons";
import { StageDots } from "../Journey";
import { useViewer } from "../Viewer";
import { MeetingPreview } from "../MeetingPreview";
import { Panel } from "../ui";
import { useOnRefresh } from "@/lib/refresh";

// Timelines are one request each, so the feed reads only the most recently active pieces.
const FEED_PIECES = 6;
const FEED_SHOWN = 6;

type Note = { at: string; who: Person | null; piece: ContentRow; text: string; kind: "comment" | "status" };

/** A creator's front page: what needs them, what is with the brand team, and what the team said. */
export function CreatorHome() {
  const { me, loading: viewerLoading } = useViewer();
  const [rows, setRows] = useState<ContentRow[] | null>(null);
  const [demo, setDemo] = useState(false);
  const [notes, setNotes] = useState<Note[] | null>(null);

  const load = useCallback(() => {
    listContents(true).then(setRows).catch((err) => {
      if (err instanceof ApiError && err.status === 503) setDemo(true);
      setRows((had) => had ?? []);
    });
  }, []);
  useEffect(() => { load(); }, [load]);
  useOnRefresh(load);

  useEffect(() => {
    if (!rows || !me) return;
    let live = true;
    const recent = rows.slice(0, FEED_PIECES);
    Promise.all(recent.map((r) => getTimeline(r.id).then((t) => ({ r, items: t.items })).catch(() => ({ r, items: [] }))))
      .then((all) => {
        if (!live) return;
        const out: Note[] = [];
        for (const { r, items } of all) for (const i of items) {
          const n = noteOf(i, r, me.id);
          if (n) out.push(n);
        }
        setNotes(out.sort((a, b) => b.at.localeCompare(a.at)).slice(0, FEED_SHOWN));
      });
    return () => { live = false; };
  }, [rows, me]);
  // Without an account there is no "someone else" to tell apart: the empty state, not a skeleton.
  const feed = rows && !viewerLoading && !me ? [] : notes;

  const groups = useMemo(() => {
    const list = rows ?? [];
    return {
      fix: list.filter((r) => r.status === "changes_requested" || r.status === "draft"),
      waiting: list.filter((r) => r.status === "in_review"),
      done: list.filter((r) => r.status === "approved" || r.status === "published"),
    };
  }, [rows]);

  const strip = [
    { label: "Needs you", value: groups.fix.length, hint: "Drafts and pieces sent back" },
    { label: "With the brand team", value: groups.waiting.length, hint: "Waiting for approval" },
    { label: "Approved", value: groups.done.filter((r) => r.status === "approved").length, hint: "Ready to publish" },
    { label: "Published", value: groups.done.filter((r) => r.status === "published").length, hint: "Live" },
  ];

  if (demo) {
    return (
      <div className="vt-card p-6 text-sm text-muted">
        Your pieces appear here once the Verytas API is connected. You can still <Link href="/review" className="font-medium text-accent hover:underline">try a review</Link> on sample data.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <section aria-label="Your pieces at a glance" className="vt-stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
        {strip.map((s) => (
          <div key={s.label} className="vt-card p-4">
            <p className="text-xs font-medium text-muted">{s.label}</p>
            <p className="mt-1.5 text-[1.6rem] font-semibold leading-none tracking-tight tabular-nums">{rows ? s.value : "·"}</p>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-subtle">{s.hint}</p>
          </div>
        ))}
      </section>

      <div className="grid gap-5 xl:grid-cols-5">
        <Panel title="Needs you" className="xl:col-span-3" scroll
          aside={<Link href="/review" className="vt-btn vt-btn-primary vt-btn-sm"><PlusIcon size={14} /> New review</Link>}>
          {rows === null ? <Skeleton /> : groups.fix.length === 0 ? (
            <p className="text-sm text-muted">Nothing to fix. Start a new review when you have something to post.</p>
          ) : (
            <PieceList rows={groups.fix} />
          )}
        </Panel>
        <Panel title="From the brand team" className="xl:col-span-2" scroll>
          {feed === null ? <Skeleton /> : feed.length === 0 ? (
            <p className="text-sm text-muted">No comments or decisions on your recent pieces yet.</p>
          ) : (
            <ul className="flex flex-col gap-3.5">
              {feed.map((n, i) => (
                <li key={`${n.piece.id}-${n.at}-${i}`}>
                  <Link href={`/review?id=${n.piece.id}`} className="group block">
                    <p className="flex items-center gap-1.5 text-[11px] text-subtle">
                      <ChatIcon size={12} />
                      <span className="truncate">{n.who?.name ?? "Brand team"} on <span className="text-muted">{n.piece.title}</span></span>
                      <span className="ml-auto shrink-0">{relativeTime(n.at)}</span>
                    </p>
                    <p className={`mt-0.5 line-clamp-2 text-sm group-hover:text-accent ${n.kind === "status" ? "font-medium" : ""}`}>{n.text}</p>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="With the brand team" scroll>
          {rows === null ? <Skeleton /> : groups.waiting.length === 0
            ? <p className="text-sm text-muted">Nothing is waiting for approval.</p>
            : <PieceList rows={groups.waiting} />}
        </Panel>
        <Panel title="Approved and published" scroll>
          {rows === null ? <Skeleton /> : groups.done.length === 0
            ? <p className="text-sm text-muted">Approved pieces show up here.</p>
            : <PieceList rows={groups.done.slice(0, 6)} />}
        </Panel>
      </div>

      <MeetingPreview side="creator" />
    </div>
  );
}

function PieceList({ rows }: { rows: ContentRow[] }) {
  return (
    <ul className="-mx-2 flex flex-col">
      {rows.map((r) => {
        const lr = r.latest_review;
        const issues = lr && lr.status === "done" ? lr.blockers ? `${lr.blockers} must-fix`
          : lr.warnings ? `${lr.warnings} to fix` : "No must-fix issues" : lr?.status === "failed" ? "Check failed" : "Checking";
        return (
          <li key={r.id}>
            <Link href={`/review?id=${r.id}`} className="group flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-sunken">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{r.title}</p>
                <p className="flex items-center gap-2 text-[11px] text-subtle">
                  <StageDots status={r.status} checked={lr?.status === "done"} />
                  <span>{STATUS_LABEL[r.status]}</span>
                  <span aria-hidden>·</span>
                  <span className={lr?.blockers ? "text-[var(--vt-blocker)]" : ""}>{issues}</span>
                </p>
              </div>
              <span className="shrink-0 text-[11px] text-subtle">{relativeTime(r.updated_at ?? r.created_at)}</span>
              <ArrowRightIcon size={14} className="shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-ink" />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function Skeleton() {
  return <ul className="flex flex-col gap-2">{[0, 1, 2].map((i) => <li key={i} className="h-11 animate-pulse rounded-lg bg-sunken" />)}</ul>;
}

/** What someone else said or decided about one of my pieces; my own actions are left out. */
function noteOf(i: TimelineItem, piece: ContentRow, myId: number): Note | null {
  if (!i.actor || i.actor.id === myId) return null;
  if (i.type === "comment") return { at: i.at, who: i.actor, piece, text: i.body, kind: "comment" };
  if (i.type === "status" && (i.to === "changes_requested" || i.to === "approved" || i.to === "published")) {
    const what = { changes_requested: "Asked for changes", approved: "Approved it", published: "Published it" }[i.to];
    return { at: i.at, who: i.actor, piece, text: i.note ? `${what}: ${i.note}` : what, kind: "status" };
  }
  if (i.type === "escalation" && (i.state === "upheld" || i.state === "cleared")) {
    const what = i.state === "cleared" ? `Cleared "${i.finding}" after your request` : `Kept "${i.finding}" after your request`;
    return { at: i.at, who: i.actor, piece, text: i.message ? `${what}: ${i.message}` : what, kind: "status" };
  }
  return null;
}

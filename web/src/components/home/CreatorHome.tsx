"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { isOffline, listContents, relativeTime, STATUS_HINT, STATUS_LABEL } from "@/lib/review-client";
import type { ContentRow } from "@/lib/types";
import { ArrowRightIcon, PlusIcon } from "../Icons";
import { NewsList } from "../news/News";
import { StageDots } from "../Journey";
import { TalkCard } from "../conversations/TalkCard";
import { Panel } from "../ui";
import { useOnRefresh } from "@/lib/refresh";
import { onLive } from "@/lib/live";

/** A creator's front page: what needs them, what is with the brand team, and what the team said. */
export function CreatorHome() {
  const [rows, setRows] = useState<ContentRow[] | null>(null);
  const [demo, setDemo] = useState(false);

  const load = useCallback(() => {
    listContents(true).then(setRows).catch((err) => {
      if (isOffline(err)) setDemo(true);
      setRows((had) => had ?? []);
    });
  }, []);
  useEffect(() => { load(); }, [load]);
  useOnRefresh(load);
  // An approval or a piece sent back moves it between the groups below: read the list again the moment it happens.
  useEffect(() => onLive((e) => { if (e.type === "review" || e.type === "escalations") load(); }), [load]);

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
          <NewsList empty="No decisions or comments on your pieces in the last two weeks." />
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

      <TalkCard side="creator" />
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
                <p className="truncate text-sm font-medium" title={r.title}>{r.title}</p>
                <p className="flex items-center gap-2 text-[11px] text-subtle">
                  <StageDots status={r.status} checked={lr?.status === "done"} />
                  <span title={STATUS_HINT[r.status]}>{STATUS_LABEL[r.status]}</span>
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

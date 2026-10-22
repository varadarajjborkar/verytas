"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiError, listContents, listPeople, relativeTime } from "@/lib/review-client";
import type { ContentRow, Overview, Person, RuleHealth } from "@/lib/types";
import { UNCLEAR } from "../DashboardView";
import { AlertIcon, ArrowRightIcon, GaugeIcon, OctagonIcon, ReviewIcon } from "../Icons";
import { StageDots } from "../Journey";
import { sinceOf } from "@/lib/queue";
import { Panel } from "../ui";
import { PipelineFlow } from "./PipelineFlow";

const QUEUE_SHOWN = 6;

/** The brand team's front page: what needs a decision now, and how the pipeline is flowing. */
export function ManagerHome({ overview, health }: { overview: Overview; health: RuleHealth[] }) {
  const [rows, setRows] = useState<ContentRow[] | null>(null);
  const [people, setPeople] = useState<Map<number, Person>>(new Map());
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    listContents(false).then(setRows).catch((err) => {
      if (err instanceof ApiError && err.status === 503) setDemo(true);
      setRows([]);
    });
    listPeople().then((ps) => setPeople(new Map(ps.map((p) => [p.id, p])))).catch(() => {});
  }, []);

  // Oldest first: whoever has waited longest is next.
  const waiting = useMemo(() => (rows ?? []).filter((r) => r.status === "in_review")
    .sort((a, b) => sinceOf(a).localeCompare(sinceOf(b))), [rows]);
  const live = rows !== null && !demo;
  // Stage totals come from the overview, which counts every piece; the list stops at 200.
  const counts = overview.content;
  const queueBlockers = waiting.reduce((n, r) => n + (r.latest_review?.blockers ?? 0), 0);
  const unclear = health.filter((h) => h.ambiguity != null && h.ambiguity >= UNCLEAR).length;
  const oldest = waiting[0];

  const facts = [
    { label: "Waiting for a decision", value: counts.in_review ?? 0, Icon: ReviewIcon, href: "/review?queue=waiting",
      hint: oldest ? `Oldest sent ${relativeTime(sinceOf(oldest))}` : "Queue is clear", tone: "accent" },
    { label: "Must-fix issues in the queue", value: live ? queueBlockers : "n/a", Icon: OctagonIcon, href: "/review?queue=waiting",
      hint: queueBlockers ? "Approving needs a noted override" : "None open", tone: queueBlockers ? "blocker" : "muted" },
    { label: "Checks that failed", value: overview.reviews.failed, Icon: AlertIcon, href: "/review?queue=all",
      hint: overview.reviews.failed ? "Saving a new version re-runs them" : "All ran", tone: overview.reviews.failed ? "warning" : "muted" },
    { label: "Rules that look unclear", value: unclear, Icon: GaugeIcon, href: "/guidelines",
      hint: unclear ? "Reviewers keep overriding them" : "None stand out", tone: unclear ? "warning" : "muted" },
  ] as const;

  return (
    <div className="flex flex-col gap-5">
      <section aria-label="Need to know" className="vt-stagger grid grid-cols-2 gap-3 lg:grid-cols-4">
        {facts.map((f) => (
          <Link key={f.label} href={f.href} className="vt-card vt-lift flex flex-col p-4">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted">
              <f.Icon size={14} className={TONE[f.tone]} />{f.label}
            </span>
            <span className="mt-1.5 text-[1.6rem] font-semibold leading-none tracking-tight tabular-nums">{f.value}</span>
            <span className="mt-2 truncate text-xs text-subtle">{f.hint}</span>
          </Link>
        ))}
      </section>

      <div className="grid gap-5 xl:grid-cols-5">
        <Panel title="How work is flowing" className="xl:col-span-3"
          aside={<span className="text-xs text-subtle">Select a stage to open it</span>}>
          <PipelineFlow counts={counts} />
        </Panel>
        <Panel title="Needs your decision" className="xl:col-span-2"
          aside={<Link href="/review?queue=waiting" className="text-xs font-medium text-accent hover:underline">Open queue</Link>}>
          {demo ? (
            <p className="text-sm text-muted">The queue needs the Verytas API. The counts here are sample data.</p>
          ) : rows === null ? (
            <ul className="flex flex-col gap-2">{[0, 1, 2].map((i) => <li key={i} className="h-11 animate-pulse rounded-lg bg-sunken" />)}</ul>
          ) : waiting.length === 0 ? (
            <p className="text-sm text-muted">Nothing is waiting. New pieces appear here when creators send them.</p>
          ) : (
            <ul className="-mx-2 flex flex-col">
              {waiting.slice(0, QUEUE_SHOWN).map((r) => (
                <li key={r.id}>
                  <Link href={`/review?id=${r.id}`} className="group flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-sunken">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{r.title}</p>
                      <p className="truncate text-[11px] text-subtle">
                        {people.get(r.created_by)?.name ?? "Creator"} · <span className="capitalize">{r.channel.replace("_", " ")}</span>
                        {" · "}sent {relativeTime(sinceOf(r))}
                      </p>
                    </div>
                    {r.latest_review?.blockers ? (
                      <span className="shrink-0 rounded-full bg-[var(--vt-blocker-bg)] px-1.5 text-[11px] font-semibold tabular-nums text-[var(--vt-blocker)]"
                        title="Must-fix issues">{r.latest_review.blockers}</span>
                    ) : r.latest_review?.overall != null ? (
                      <span className="shrink-0 text-xs tabular-nums text-muted">{Math.round(r.latest_review.overall * 100)}%</span>
                    ) : null}
                    <ArrowRightIcon size={14} className="shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-ink" />
                  </Link>
                </li>
              ))}
              {waiting.length > QUEUE_SHOWN && (
                <li className="px-2 pt-1 text-[11px] text-subtle">and {waiting.length - QUEUE_SHOWN} more in the queue</li>
              )}
            </ul>
          )}
        </Panel>
      </div>

      {live && rows.length > 0 && (
        <Panel title="Recently active"
          aside={<Link href="/review?queue=all" className="text-xs font-medium text-accent hover:underline">All pieces</Link>}>
          <ul className="grid gap-x-6 gap-y-1 md:grid-cols-2">
            {rows.slice(0, 8).map((r) => (
              <li key={r.id}>
                <Link href={`/review?id=${r.id}`} className="flex items-center gap-3 rounded-lg py-1.5 text-sm hover:text-accent">
                  <StageDots status={r.status} checked={r.latest_review?.status === "done"} />
                  <span className="min-w-0 flex-1 truncate">{r.title}</span>
                  <span className="shrink-0 text-[11px] text-subtle">{relativeTime(r.updated_at ?? r.created_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

const TONE = {
  accent: "text-accent",
  blocker: "text-[var(--vt-blocker)]",
  warning: "text-[var(--vt-warning)]",
  muted: "text-subtle",
} as const;

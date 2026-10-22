"use client";

import { relativeTime, STATUS_LABEL } from "@/lib/review-client";
import type { ContentRow, Person } from "@/lib/types";
import { ArrowRightIcon } from "../Icons";
import { StageDots } from "../Journey";

export type Queue = "waiting" | "creator" | "approved" | "all";

export const QUEUES: Record<Queue, { label: string; title: string; lead: string; statuses: ContentRow["status"][] | null }> = {
  waiting: { label: "Waiting", title: "Waiting for a decision", lead: "Sent by creators. Oldest first: approve, or send back with a note.",
    statuses: ["in_review"] },
  creator: { label: "With creator", title: "With the creator", lead: "Drafts and pieces sent back for changes. Nothing to do until they resend.",
    statuses: ["draft", "changes_requested"] },
  approved: { label: "Approved", title: "Approved and published", lead: "Cleared pieces. Approved ones can still be marked published or sent back.",
    statuses: ["approved", "published"] },
  all: { label: "All", title: "Every piece", lead: "Everything you can see, newest activity first.", statuses: null },
};

export const inQueue = (q: Queue) => (r: ContentRow) => QUEUES[q].statuses?.includes(r.status) ?? true;

/** The brand team's landing view in Review: the selected queue as a table, in place of a new-review form. */
export function QueueOverview({ queue, rows, people, loading, onSelect }: {
  queue: Queue;
  rows: ContentRow[];
  people: Map<number, Person>;
  loading: boolean;
  onSelect: (id: number) => void;
}) {
  const q = QUEUES[queue];
  // The waiting queue is first come, first served; the others read newest first.
  const shown = queue === "waiting"
    ? [...rows].sort((a, b) => (a.updated_at ?? a.created_at).localeCompare(b.updated_at ?? b.created_at))
    : rows;
  return (
    <section className="vt-card min-w-0 p-4 md:p-6" aria-label={q.title}>
      <h2 className="text-lg font-semibold tracking-tight">{q.title}</h2>
      <p className="mb-5 mt-1 text-sm text-muted">{q.lead}</p>
      {loading && rows.length === 0 ? (
        <ul className="flex flex-col gap-2">{[0, 1, 2, 3].map((i) => <li key={i} className="h-12 animate-pulse rounded-lg bg-sunken" />)}</ul>
      ) : shown.length === 0 ? (
        <p className="rounded-xl bg-sunken px-4 py-6 text-center text-sm text-muted">
          {queue === "waiting" ? "The queue is clear." : "Nothing here."}
        </p>
      ) : (
        <div className="-mx-4 overflow-x-auto md:-mx-6">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-[11px] font-medium uppercase tracking-wide text-subtle">
                <th scope="col" className="py-2 pl-4 pr-3 font-medium md:pl-6">Piece</th>
                <th scope="col" className="px-3 py-2 font-medium">Stage</th>
                <th scope="col" className="px-3 py-2 font-medium">Latest check</th>
                <th scope="col" className="px-3 py-2 font-medium">{queue === "waiting" ? "Waiting" : "Updated"}</th>
                <th scope="col" className="w-8 py-2 pr-4 md:pr-6"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {shown.map((r) => {
                const lr = r.latest_review;
                return (
                  <tr key={r.id} onClick={() => onSelect(r.id)} className="group cursor-pointer hover:bg-sunken/60">
                    <td className="max-w-0 py-2.5 pl-4 pr-3 md:pl-6">
                      <button type="button" onClick={(e) => { e.stopPropagation(); onSelect(r.id); }}
                        className="block w-full truncate text-left font-medium hover:text-accent">{r.title}</button>
                      <p className="truncate text-[11px] text-subtle">
                        {people.get(r.created_by)?.name ?? "Unknown"} · <span className="capitalize">{r.channel.replace("_", " ")}</span>
                        {r.version_count > 1 ? ` · v${r.version_count}` : ""}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5">
                      <span className="flex items-center gap-2">
                        <StageDots status={r.status} checked={lr?.status === "done"} />
                        <span className="text-xs text-muted">{STATUS_LABEL[r.status]}</span>
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs">
                      {!lr ? <span className="text-subtle">Not checked</span>
                        : lr.status === "failed" ? <span className="text-[var(--vt-warning)]">Failed</span>
                          : lr.status !== "done" ? <span className="text-subtle">Checking</span>
                            : (
                              <span className="flex items-center gap-2">
                                {lr.overall != null && <span className="tabular-nums">{Math.round(lr.overall * 100)}%</span>}
                                {lr.blockers > 0 && (
                                  <span className="rounded-full bg-[var(--vt-blocker-bg)] px-1.5 font-semibold tabular-nums text-[var(--vt-blocker)]">
                                    {lr.blockers} must-fix
                                  </span>
                                )}
                                {lr.blockers === 0 && lr.warnings > 0 && <span className="text-muted">{lr.warnings} to fix</span>}
                              </span>
                            )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted">{relativeTime(r.updated_at ?? r.created_at)}</td>
                    <td className="py-2.5 pr-4 md:pr-6">
                      <ArrowRightIcon size={14} className="text-subtle transition group-hover:translate-x-0.5 group-hover:text-ink" />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

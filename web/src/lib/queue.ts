// The brand team's queue: which pieces sit where, how urgent each one is, and
// how to sort, filter and group them. Pure functions, so the queue page, the
// dashboard and the nav all rank pieces the same way.

import type { ContentRow } from "./types";

export type Queue = "waiting" | "escalated" | "creator" | "approved" | "all";

export const QUEUES: Record<Queue, { label: string; title: string; test: (r: ContentRow) => boolean }> = {
  waiting: { label: "Waiting", title: "Waiting for a decision",
    test: (r) => r.status === "in_review" },
  escalated: { label: "Escalated", title: "Escalated to a person",
    test: (r) => (r.open_escalations ?? 0) > 0 },
  creator: { label: "With creator", title: "With the creator",
    test: (r) => r.status === "draft" || r.status === "changes_requested" },
  approved: { label: "Approved", title: "Approved and published",
    test: (r) => r.status === "approved" || r.status === "published" },
  all: { label: "All", title: "Every piece", test: () => true },
};
export const QUEUE_ORDER: Queue[] = ["waiting", "escalated", "creator", "approved", "all"];
export const isQueue = (q: string | null): q is Queue => q != null && Object.hasOwn(QUEUES, q);

/** How long a piece has sat where it is; older API builds lack status_since. */
export const sinceOf = (r: ContentRow) => r.status_since ?? r.updated_at ?? r.created_at;
const daysSince = (iso: string, now: number) => Math.max(0, (now - new Date(iso).getTime()) / 86_400_000);

/**
 * Urgency of a piece for the brand team. Must-fix issues and a creator waiting on
 * a person weigh most, then time in the queue (capped, so an old piece doesn't
 * bury a fresh blocker), then softer signals. Only pieces that need a decision rank.
 */
export function priority(r: ContentRow, now = Date.now()): number {
  if (r.status !== "in_review" && !(r.open_escalations ?? 0)) return 0;
  const lr = r.latest_review;
  return (lr?.blockers ?? 0) * 3 + (lr?.warnings ?? 0) + (r.open_escalations ?? 0) * 4
    + Math.min(daysSince(sinceOf(r), now), 10) * 0.6 + (r.rechecked_for_event ? 1.5 : 0)
    + (lr?.status === "failed" ? 2 : 0) + (r.status === "in_review" ? 1 : 0);
}
export const priorityBand = (p: number): "high" | "medium" | "low" | null =>
  p >= 7 ? "high" : p >= 3.5 ? "medium" : p > 0 ? "low" : null;

export type Sort = "priority" | "waiting" | "recent" | "score" | "issues" | "creator";
export const SORTS: Record<Sort, string> = {
  priority: "Priority",
  waiting: "Waiting longest",
  recent: "Recent activity",
  score: "Lowest score first",
  issues: "Most must-fix",
  creator: "Creator, A to Z",
};
export const isSort = (s: string | null): s is Sort => s != null && Object.hasOwn(SORTS, s);

export function sortRows(rows: ContentRow[], sort: Sort, nameOf: (id: number) => string): ContentRow[] {
  const now = Date.now();
  const by: Record<Sort, (a: ContentRow, b: ContentRow) => number> = {
    priority: (a, b) => priority(b, now) - priority(a, now) || sinceOf(a).localeCompare(sinceOf(b)),
    waiting: (a, b) => sinceOf(a).localeCompare(sinceOf(b)),
    recent: (a, b) => (b.updated_at ?? b.created_at).localeCompare(a.updated_at ?? a.created_at),
    score: (a, b) => (a.latest_review?.overall ?? 2) - (b.latest_review?.overall ?? 2),
    issues: (a, b) => (b.latest_review?.blockers ?? 0) - (a.latest_review?.blockers ?? 0)
      || (b.latest_review?.warnings ?? 0) - (a.latest_review?.warnings ?? 0),
    creator: (a, b) => nameOf(a.created_by).localeCompare(nameOf(b.created_by)),
  };
  return [...rows].sort(by[sort]);
}

export type Signal = "mustfix" | "escalated" | "event" | "failed" | "clean";
export const SIGNALS: Record<Signal, { label: string; test: (r: ContentRow) => boolean }> = {
  mustfix: { label: "Has must-fix issues", test: (r) => (r.latest_review?.blockers ?? 0) > 0 },
  escalated: { label: "Escalated by the creator", test: (r) => (r.open_escalations ?? 0) > 0 },
  event: { label: "Re-checked after an event change", test: (r) => r.rechecked_for_event != null },
  failed: { label: "Check failed", test: (r) => r.latest_review?.status === "failed" },
  clean: { label: "No must-fix issues", test: (r) => r.latest_review?.status === "done" && r.latest_review.blockers === 0 },
};

export type Group = "none" | "creator" | "event" | "stage" | "channel";
export const GROUPS: Record<Group, string> = { none: "No grouping", creator: "By creator", event: "By event", stage: "By stage",
  channel: "By channel" };

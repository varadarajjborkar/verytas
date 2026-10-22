// Where a piece is on its way from first draft to published. The home pages
// draw it as a row of dots and the review screen as a map; both read the same
// stages, so the creator and the brand team describe a piece the same way.

import type { ContentStatus, Person, Timeline, TimelineItem } from "./types";

export const STAGES = ["Written", "Checked", "Sent for approval", "Approved", "Published"] as const;

/** Index into STAGES of the furthest stage reached, or -1 once withdrawn. */
export function stageOf(status: ContentStatus, checked: boolean): number {
  switch (status) {
    case "draft": return checked ? 1 : 0;
    case "changes_requested": return 1;
    case "in_review": return 2;
    case "approved": return 3;
    case "published": return 4;
    case "withdrawn": return -1;
  }
}

export type Milestone = {
  label: (typeof STAGES)[number];
  state: "done" | "current" | "todo";
  at: string | null;
  who: Person | null;
  detail: string | null;
};

export type Journey = {
  milestones: Milestone[];
  /** How many times the brand team sent it back. Each round is a loop on the map. */
  rounds: number;
  lastSentBack: { at: string; who: Person | null; note: string | null } | null;
  withdrawn: boolean;
  versions: number;
  comments: number;
  decisions: number;
};

type Of<T extends TimelineItem["type"]> = Extract<TimelineItem, { type: T }>;
const last = <T>(xs: T[]) => (xs.length ? xs[xs.length - 1] : undefined);

export function journey(t: Timeline): Journey {
  const items = t.items;
  const versions = items.filter((i): i is Of<"version"> => i.type === "version");
  const reviews = items.filter((i): i is Of<"review"> => i.type === "review");
  const moves = items.filter((i): i is Of<"status"> => i.type === "status");
  const movedTo = (s: ContentStatus) => last(moves.filter((m) => m.to === s));
  const review = last(reviews.filter((r) => r.status === "done")) ?? last(reviews);
  const backs = moves.filter((m) => m.to === "changes_requested");
  const lastBack = last(backs);

  const current = stageOf(t.status, reviews.some((r) => r.status === "done"));
  const withdrawn = current < 0;
  // A withdrawn piece keeps the stages it really reached, with none marked current.
  const reached = withdrawn
    ? Math.max(versions.length ? 0 : -1, reviews.length ? 1 : -1, movedTo("in_review") ? 2 : -1, movedTo("approved") ? 3 : -1)
    : current;

  const sent = movedTo("in_review");
  const approved = movedTo("approved");
  const published = movedTo("published");
  const evidence: [string | null, Person | null, string | null][] = [
    [versions[0]?.at ?? null, t.author, versions.length > 1 ? `${versions.length} versions` : null],
    [review?.at ?? null, null, review ? reviewDetail(review) : null],
    [sent?.at ?? null, sent?.actor ?? null, sent?.note ?? null],
    [approved?.at ?? null, approved?.actor ?? null, approved?.note ?? null],
    [published?.at ?? null, published?.actor ?? null, null],
  ];
  const milestones = STAGES.map((label, i): Milestone => ({
    label,
    state: i < reached || (withdrawn && i === reached) ? "done" : i === reached ? "current" : "todo",
    at: i <= reached ? evidence[i][0] : null,
    who: i <= reached ? evidence[i][1] : null,
    detail: i <= reached ? evidence[i][2] : null,
  }));
  return {
    milestones,
    rounds: backs.length,
    lastSentBack: lastBack ? { at: lastBack.at, who: lastBack.actor, note: lastBack.note } : null,
    withdrawn,
    versions: versions.length,
    comments: items.filter((i) => i.type === "comment").length,
    decisions: items.filter((i) => i.type === "decision").length,
  };
}

function reviewDetail(r: Of<"review">): string {
  if (r.status === "failed") return "Check failed";
  if (r.status !== "done") return "Checking...";
  const issues = r.blockers ? `${r.blockers} must-fix` : r.warnings ? `${r.warnings} to fix` : "No must-fix issues";
  return r.score == null ? issues : `${Math.round(r.score * 100)}% · ${issues}`;
}

"use client";

import { Fragment, useMemo, useState } from "react";
import { addComment, relativeTime } from "@/lib/review-client";
import { ROLE_LABEL } from "@/lib/roles";
import type { ContentStatus, Timeline, TimelineItem } from "@/lib/types";
import { ChatIcon, CheckIcon, OctagonIcon, RefreshIcon, ReviewIcon } from "../Icons";
import { useToast } from "../Toaster";
import { ACTION_LABEL, REASONS } from "./DecisionControls";

type Comment = Extract<TimelineItem, { type: "comment" }>;

const MOVE: Partial<Record<ContentStatus, string>> = {
  in_review: "sent it for approval",
  changes_requested: "asked for changes",
  approved: "approved it",
  published: "marked it published",
  withdrawn: "withdrew it",
  draft: "moved it back to draft",
};
const REASON_LABEL: Record<string, string> = Object.fromEntries(REASONS.map((r) => [r.code, r.label]));

/**
 * The piece's shared history, oldest first, like a pull request's conversation:
 * versions, checks, status moves, decisions and comments, with a box to add one.
 * The creator and the brand team read the same feed.
 */
export function Activity({ timeline, contentId, versionId, onPosted }: {
  timeline: Timeline | null;
  contentId: number;
  versionId: number | null;
  onPosted: () => void;
}) {
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  // Replies hang under the comment they answer; everything else stays in time order.
  const { feed, replies } = useMemo(() => {
    const items = timeline?.items ?? [];
    // Threads are shown one level deep, so a reply to a reply joins the thread's first comment.
    const parent = new Map(items.flatMap((i) => (i.type === "comment" ? [[i.id, i.parent_id] as const] : [])));
    const rootOf = (id: number) => {
      let at = id;
      for (let hops = 0; hops < 50; hops++) {
        const up = parent.get(at);
        if (up == null || !parent.has(up)) return at;
        at = up;
      }
      return at;
    };
    const replies = new Map<number, Comment[]>();
    const feed: TimelineItem[] = [];
    for (const i of items) {
      const root = i.type === "comment" && i.parent_id != null ? rootOf(i.id) : null;
      if (i.type === "comment" && root != null && root !== i.id) replies.set(root, [...(replies.get(root) ?? []), i]);
      else feed.push(i);
    }
    return { feed, replies };
  }, [timeline]);

  async function post() {
    const body = text.trim();
    if (!body) return;
    setBusy(true);
    try {
      // A reply goes on the top of its thread, so threads stay one level deep.
      await addComment(contentId, body, versionId ?? undefined, replyTo ? (replyTo.parent_id ?? replyTo.id) : undefined);
      setText("");
      setReplyTo(null);
      onPosted();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't post the comment", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  if (!timeline) {
    return <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-sunken" />)}</div>;
  }
  return (
    <div className="flex flex-col gap-4">
      <ol className="relative flex max-h-[32rem] flex-col gap-2.5 overflow-y-auto pr-1">
        {feed.map((i, n) => (
          <Fragment key={`${i.type}-${i.at}-${n}`}>
            {n > 0 && <Divider before={feed[n - 1].at} after={i.at} />}
            <li>
              {i.type === "comment" ? (
                <CommentItem c={i} replies={replies.get(i.id) ?? []} onReply={setReplyTo} />
              ) : (
                <EventItem i={i} />
              )}
            </li>
          </Fragment>
        ))}
      </ol>
      <div className="border-t border-line pt-3">
        {replyTo && (
          <p className="mb-1.5 flex items-center gap-2 text-[11px] text-muted">
            Replying to {replyTo.actor?.name ?? "comment"}
            <button type="button" onClick={() => setReplyTo(null)} className="text-subtle hover:text-ink">Cancel</button>
          </p>
        )}
        <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={5000} aria-label="Add a comment"
          placeholder={replyTo ? "Write a reply" : "Leave a comment for everyone on this piece"} className="vt-input min-h-16 text-sm"
          onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void post(); }} />
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-[11px] text-subtle">Saved with the current version</span>
          <button type="button" disabled={busy || !text.trim()} onClick={post} className="vt-btn vt-btn-primary vt-btn-sm">
            {busy ? "Posting..." : replyTo ? "Reply" : "Comment"}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * A hairline between entries. Across the full width when the entries fall on different days (in the
 * reader's own time zone), and shorter, centred, between entries of the same day: the change of day reads
 * at a glance without a date header taking a line of its own.
 */
function Divider({ before, after }: { before: string; after: string }) {
  const day = (at: string) => new Date(at).toDateString();
  const newDay = day(before) !== day(after);
  return (
    <li role="presentation" className={`h-px shrink-0 bg-[var(--vt-line)] opacity-70 ${newDay ? "w-full" : "mx-auto w-[79%]"}`}>
      {newDay && <span className="sr-only">{new Date(after).toLocaleDateString(undefined, { dateStyle: "medium" })}</span>}
    </li>
  );
}

function Who({ i }: { i: TimelineItem }) {
  if (!i.actor) return <span className="font-medium">Verytas</span>;
  return (
    <span>
      <span className="font-medium">{i.actor.name}</span>
      <span className="text-subtle"> · {ROLE_LABEL[i.actor.role] ?? i.actor.role}</span>
    </span>
  );
}

function When({ at }: { at: string }) {
  return <time dateTime={at} title={new Date(at).toLocaleString()} className="shrink-0 text-[11px] text-subtle">{relativeTime(at)}</time>;
}

function CommentItem({ c, replies, onReply }: { c: Comment; replies: Comment[]; onReply: (c: Comment) => void }) {
  return (
    <div className="rounded-xl border border-line bg-raised p-3">
      <p className="flex items-center gap-2 text-xs">
        <ChatIcon size={13} className="shrink-0 text-accent" />
        <span className="min-w-0 flex-1 truncate"><Who i={c} />{c.version ? <span className="text-subtle"> · on v{c.version}</span> : null}</span>
        <When at={c.at} />
      </p>
      <p className="mt-1.5 whitespace-pre-wrap text-sm leading-6">{c.body}</p>
      {replies.length > 0 && (
        <ul className="mt-2.5 flex flex-col gap-2 border-l-2 border-line pl-3">
          {replies.map((r) => (
            <li key={r.id}>
              <p className="flex items-center gap-2 text-xs"><span className="min-w-0 flex-1 truncate"><Who i={r} /></span><When at={r.at} /></p>
              <p className="mt-0.5 whitespace-pre-wrap text-sm leading-6">{r.body}</p>
            </li>
          ))}
        </ul>
      )}
      <button type="button" onClick={() => onReply(c)} className="mt-1.5 text-[11px] font-medium text-muted hover:text-accent">Reply</button>
    </div>
  );
}

function EventItem({ i }: { i: Exclude<TimelineItem, Comment> }) {
  let icon = <ReviewIcon size={13} className="text-subtle" />;
  let line: React.ReactNode = null;
  let note: string | null = null;
  if (i.type === "version") {
    line = <><Who i={i} /> saved version {i.version}</>;
  } else if (i.type === "review") {
    const failed = i.status === "failed";
    icon = failed ? <OctagonIcon size={13} className="text-[var(--vt-warning)]" />
      : i.blockers ? <OctagonIcon size={13} className="text-[var(--vt-blocker)]" /> : <CheckIcon size={13} className="text-[var(--vt-ok)]" />;
    line = failed ? <>Check of v{i.version} failed</>
      : i.status !== "done" ? <>Checking v{i.version}</>
        : <>Checked v{i.version}: {i.score != null ? `${Math.round(i.score * 100)}%, ` : ""}
          {i.blockers ? `${i.blockers} must-fix` : "no must-fix"}{i.warnings ? `, ${i.warnings} to fix` : ""}</>;
  } else if (i.type === "status") {
    icon = i.to === "changes_requested" ? <RefreshIcon size={13} className="text-[var(--vt-warning)]" />
      : i.to === "approved" || i.to === "published" ? <CheckIcon size={13} className="text-[var(--vt-ok)]" />
        : <ReviewIcon size={13} className="text-accent" />;
    line = <><Who i={i} /> {MOVE[i.to] ?? `moved it to ${i.to}`}</>;
    note = i.note;
  } else if (i.type === "escalation") {
    icon = <ChatIcon size={13} className={i.state === "raised" ? "text-accent" : i.state === "cleared" ? "text-[var(--vt-ok)]" : "text-muted"} />;
    line = i.state === "raised"
      ? <><Who i={i} /> asked the brand team to review &ldquo;{i.finding}&rdquo;</>
      : i.state === "withdrawn" ? <><Who i={i} /> withdrew the request on &ldquo;{i.finding}&rdquo;</>
        : <><Who i={i} /> {i.state === "cleared" ? "cleared" : "upheld"} &ldquo;{i.finding}&rdquo; after review</>;
    note = i.message;
  } else if (i.type === "event") {
    icon = <RefreshIcon size={13} className="text-accent" />;
    line = <>Event &ldquo;{i.event}&rdquo; {i.change === "created" ? "started" : i.change === "cancelled" ? "was cancelled" : "changed"}: re-checked against it</>;
  } else if (i.type === "decision") {
    icon = <CheckIcon size={13} className="text-muted" />;
    line = <><Who i={i} /> {ACTION_LABEL[i.action].toLowerCase()} &ldquo;{i.finding}&rdquo;
      {i.reason_code ? <span className="text-muted"> ({REASON_LABEL[i.reason_code] ?? i.reason_code})</span> : null}</>;
    note = i.reason;
  }
  return (
    <div className="flex gap-2.5 px-1 text-xs">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <p className="leading-5">{line}</p>
        {note && <p className="mt-0.5 text-muted">&ldquo;{note}&rdquo;</p>}
      </div>
      <When at={i.at} />
    </div>
  );
}

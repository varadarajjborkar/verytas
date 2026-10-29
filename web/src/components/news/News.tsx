"use client";

// News from the other side, where each side waits on the other: a creator hears the brand team approve, send
// back, answer a request or decide a dispute; the brand team hears a creator send a piece in, escalate an
// issue or save a new version (backend services/review_news.py). Shown as the first panel on each dashboard
// and, briefly, as a notice from the bottom on sign-in or the moment something arrives. Opening a piece marks
// its news read (ReviewView).

import Link from "next/link";
import { useEffect, useSyncExternalStore } from "react";
import { getNews, relativeTime, type NewsItem } from "@/lib/review-client";
import { onLive, REVIEWS_SEEN_EVENT } from "@/lib/live";
import { useViewer } from "../Viewer";
import { ArrowRightIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Panel } from "../ui";

type Tone = "ok" | "warn" | "bad" | "info";
const LOOK: Record<string, { label: string; tone: Tone; action: string }> = {
  approved: { label: "Approved", tone: "ok", action: "Publish it" },
  published: { label: "Published", tone: "ok", action: "Open" },
  sent_back: { label: "Sent back", tone: "warn", action: "Make the changes" },
  status: { label: "Status changed", tone: "info", action: "Open" },
  cleared: { label: "Issue cleared", tone: "ok", action: "Open" },
  confirmed: { label: "Issue confirmed", tone: "warn", action: "Fix it" },
  escalation_cleared: { label: "Request granted", tone: "ok", action: "Open" },
  escalation_upheld: { label: "Issue stands", tone: "bad", action: "Fix it" },
  dispute_overturned: { label: "Dispute accepted", tone: "ok", action: "Open" },
  dispute_upheld: { label: "Dispute: issue stands", tone: "bad", action: "Fix it" },
  dispute_escalated: { label: "Dispute to decide", tone: "warn", action: "Decide" },
  dispute_passed: { label: "Dispute with the brand team", tone: "info", action: "Open" },
  comment: { label: "Comment", tone: "info", action: "Reply" },
  submitted: { label: "Sent for approval", tone: "info", action: "Review it" },
  escalated: { label: "Escalated", tone: "warn", action: "Answer it" },
  new_version: { label: "New version", tone: "info", action: "Review it" },
};
const TONE: Record<Tone, string> = {
  ok: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
  warn: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
  bad: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)]",
  info: "bg-accent/12 text-accent",
};
const look = (kind: string) => LOOK[kind] ?? LOOK.status;
// Everything opens the piece: that is where it is acted on (an escalation too, beside its issue), and opening
// it is what marks its news read.
const hrefOf = (i: NewsItem) => `/review?id=${i.content_id}`;

/** One store per tab, however many places show news (the nav badge and notice, the dashboard panel):
 * one request per trigger, shared. Read on first use, the moment something happens (live), when a piece is
 * opened, on focus, and each minute as a fallback. */
type NewsState = { items: NewsItem[] | null; unread: number };
let news: NewsState = { items: null, unread: 0 };
const subscribers = new Set<() => void>();
let inFlight: Promise<void> | null = null;
let stopTriggers: (() => void) | null = null;

function refresh(): Promise<void> {
  inFlight ??= getNews()
    .then((n) => { news = { items: n.items, unread: n.unread }; })
    .catch(() => { news = { ...news, items: news.items ?? [] }; })
    .finally(() => { inFlight = null; subscribers.forEach((f) => f()); });
  return inFlight;
}

function subscribe(onChange: () => void): () => void {
  subscribers.add(onChange);
  if (!stopTriggers) {
    void refresh();
    const tick = () => { if (!document.hidden) void refresh(); };
    const t = setInterval(tick, 60_000);
    window.addEventListener("focus", tick);
    window.addEventListener(REVIEWS_SEEN_EVENT, tick);
    const off = onLive((e) => { if (e.type === "review" || e.type === "escalations") void refresh(); });
    stopTriggers = () => { clearInterval(t); window.removeEventListener("focus", tick); window.removeEventListener(REVIEWS_SEEN_EVENT, tick); off(); };
  }
  return () => {
    subscribers.delete(onChange);
    if (!subscribers.size) { stopTriggers?.(); stopTriggers = null; }
  };
}

const EMPTY: NewsState = { items: null, unread: 0 };

export function useNews(): NewsState {
  const { me } = useViewer();
  const state = useSyncExternalStore(me ? subscribe : noop, () => news, () => EMPTY);
  return me ? state : EMPTY;
}
const noop = () => () => {};

/** The newest unread item on each piece: one line per piece that waits on this person. */
function unreadByPiece(items: NewsItem[]): NewsItem[] {
  const seen = new Set<number>();
  return items.filter((i) => i.unread && !seen.has(i.content_id) && seen.add(i.content_id));
}

function Chip({ kind }: { kind: string }) {
  const l = look(kind);
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONE[l.tone]}`}>{l.label}</span>;
}

/** The first panel under each dashboard's tiles, beside what waits on the person: everything from the other side
 * in the last two weeks, the unread marked, scrolling inside its box like the panels around it. */
export function NewsPanel({ empty, className = "" }: { empty: string; className?: string }) {
  return (
    <Panel title="Since you were last here" className={className} scroll aside={<UnreadCount />}>
      <NewsList empty={empty} />
    </Panel>
  );
}

/** "3 new" beside the panel title: pieces with unread news, the same count as the nav badge. */
export function UnreadCount() {
  const { items } = useNews();
  const n = unreadByPiece(items ?? []).length;
  if (!n) return null;
  return <span className="rounded-full bg-accent/12 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-accent">{n} new</span>;
}

/** Everything from the last two weeks, read and unread, for a dashboard panel. */
export function NewsList({ empty }: { empty: string }) {
  const { items } = useNews();
  if (items === null) {
    return <ul className="flex flex-col gap-2">{[0, 1, 2].map((i) => <li key={i} className="h-11 animate-pulse rounded-lg bg-sunken" />)}</ul>;
  }
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {items.slice(0, 20).map((i, n) => (
        <li key={`${i.content_id}-${i.kind}-${i.at}-${n}`}>
          <Link href={hrefOf(i)} className="group block">
            <p className="flex items-center gap-2 text-[11px] text-subtle">
              {i.unread && <span role="img" aria-label="New" className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />}
              <Chip kind={i.kind} />
              <span className="truncate text-muted">{i.title}</span>
              <span className="ml-auto shrink-0">{relativeTime(i.at)}</span>
            </p>
            <p className={`mt-1 line-clamp-2 text-sm group-hover:text-accent ${i.unread ? "font-medium" : ""}`}>
              {i.text}{i.note ? ` "${i.note}"` : ""}
            </p>
            {i.unread && (
              <p className="mt-1 flex items-center gap-1 text-xs font-semibold text-accent">
                {look(i.kind).action} <ArrowRightIcon size={12} className="transition group-hover:translate-x-0.5" />
              </p>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

const SHOWN_KEY = "vt-news-shown";
const TOAST_KIND = { ok: "success", warn: "warning", bad: "warning", info: "info" } as const;
// What this tab announced, per person: the floor when storage is blocked, so a refresh doesn't announce again.
const announced = new Map<string, string>();

/**
 * A short notice from the bottom of the window that fades on its own: on sign-in (or the first page after it)
 * for what arrived while the person was away, and while they are here for each new thing the moment it lands.
 * The detail lives in the dashboard panel, so the notice only says that something happened. Shown once per
 * item: what this browser already announced isn't announced again.
 */
export function NewsNotice() {
  const { me } = useViewer();
  const { items } = useNews();
  const toast = useToast();
  const key = me ? `${SHOWN_KEY}:${me.id}` : null;
  useEffect(() => {
    if (!key || !items) return;
    let since = announced.get(key) ?? "";
    try { const stored = localStorage.getItem(key) ?? ""; if (stored > since) since = stored; } catch { /* this tab's memory only */ }
    const fresh = unreadByPiece(items).filter((i) => i.at > since);
    if (!fresh.length) return;
    announced.set(key, fresh[0].at);
    try { localStorage.setItem(key, fresh[0].at); } catch { /* announced again on the next visit */ }
    const top = fresh[0], l = look(top.kind);
    toast(fresh.length === 1
      ? { kind: TOAST_KIND[l.tone], title: `${l.label}: ${top.title}`, detail: top.text }
      : { kind: "info", title: `News on ${fresh.length} pieces`, detail: `${l.label}: ${top.title}, and ${fresh.length - 1} more` });
  }, [key, items, toast]);
  return null;
}

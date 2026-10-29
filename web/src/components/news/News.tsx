"use client";

// News from the other side, where each side waits on the other: a creator hears the brand team approve, send
// back, answer a request or decide a dispute; the brand team hears a creator send a piece in, escalate an
// issue or save a new version (backend services/review_news.py). Shown three ways: a highlight at the top
// of the dashboard while anything is unread, the full list in a panel, and a notice on sign-in or the
// moment something arrives. Opening a piece marks its news read (ReviewView).

import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { getNews, relativeTime, type NewsItem } from "@/lib/review-client";
import { onLive, REVIEWS_SEEN_EVENT } from "@/lib/live";
import { useViewer } from "../Viewer";
import { ArrowRightIcon, CloseIcon } from "../Icons";

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

/** One store per tab, however many places show news (the nav notice, the dashboard highlight and list):
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

/** Top of the dashboard, only while something is unread: what happened, on which piece, and the next step. */
export function NewsHighlights() {
  const { items } = useNews();
  const fresh = unreadByPiece(items ?? []);
  if (!fresh.length) return null;
  return (
    <section aria-label="Since you were last here" className="vt-card vt-pop border-accent/40 p-4 md:p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold">Since you were last here</h2>
        <p className="text-xs text-subtle">{fresh.length} piece{fresh.length === 1 ? "" : "s"} with news</p>
      </div>
      <ul className="mt-3 flex flex-col gap-2">
        {fresh.slice(0, 5).map((i) => (
          <li key={`${i.content_id}-${i.at}`}>
            <Link href={hrefOf(i)} className="group flex items-center gap-3 rounded-xl border border-line bg-raised px-3 py-2.5 hover:border-accent/60">
              <Chip kind={i.kind} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{i.title}</span>
                <span className="block truncate text-xs text-muted">
                  {i.text}{i.note ? ` "${i.note}"` : ""}
                </span>
              </span>
              <span className="hidden shrink-0 text-[11px] text-subtle sm:inline">{relativeTime(i.at)}</span>
              <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-accent">
                {look(i.kind).action} <ArrowRightIcon size={13} className="transition group-hover:translate-x-0.5" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {fresh.length > 5 && <p className="mt-2 text-xs text-subtle">And {fresh.length - 5} more below.</p>}
    </section>
  );
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
      {items.slice(0, 12).map((i, n) => (
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
          </Link>
        </li>
      ))}
    </ul>
  );
}

const SHOWN_KEY = "vt-news-shown";

/**
 * The notice: on sign-in (or the first page after it), what arrived while the person was away; and while they
 * are here, each new thing the moment it lands. Shown once per item: what was already shown in this browser
 * isn't shown again, and opening the piece reads it anyway.
 */
export function NewsNotice() {
  const { me } = useViewer();
  const { items } = useNews();
  const key = me ? `${SHOWN_KEY}:${me.id}` : null;
  // What this browser already showed, read once per person; this visit's notice stays until dismissed.
  const before = useMemo(() => {
    if (!key || typeof window === "undefined") return "";
    try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
  }, [key]);
  const [dismissed, setDismissed] = useState("");
  const since = dismissed > before ? dismissed : before;
  const shown = unreadByPiece(items ?? []).filter((i) => i.at > since).slice(0, 4);
  const newest = shown[0]?.at;
  useEffect(() => {
    if (!key || !newest) return;
    try { if ((localStorage.getItem(key) ?? "") < newest) localStorage.setItem(key, newest); } catch { /* shows again next time */ }
  }, [key, newest]);
  const close = () => setDismissed(newest ?? "");
  if (!shown.length) return null;
  return (
    <aside role="status" aria-label="News" className="vt-pop fixed right-4 top-20 z-50 w-[min(24rem,calc(100vw-2rem))] rounded-2xl border border-line bg-surface p-4 shadow-[var(--vt-shadow-pop)]">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold">{shown.length === 1 ? "New since you were last here" : `News on ${shown.length} pieces`}</p>
        <button type="button" onClick={close} aria-label="Dismiss" className="rounded-md p-1 text-subtle hover:bg-sunken hover:text-ink">
          <CloseIcon size={14} />
        </button>
      </div>
      <ul className="mt-2 flex flex-col gap-2">
        {shown.map((i) => (
          <li key={`${i.content_id}-${i.at}`}>
            <Link href={hrefOf(i)} onClick={close} className="group flex items-center gap-2.5 rounded-lg px-1 py-1 hover:bg-sunken">
              <Chip kind={i.kind} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium group-hover:text-accent">{i.title}</span>
                <span className="block truncate text-xs text-muted">{i.text}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}

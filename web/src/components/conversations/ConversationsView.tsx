"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  type ChatMessage, type Contact, CONVERSATIONS_SEEN_EVENT, type ConversationRow, type LiveEvent, listContacts,
  listConversations, openConversation,
} from "@/lib/conversations-client";
import { relativeTime, STATUS_LABEL } from "@/lib/review-client";
import { ROLE_LABEL } from "@/lib/roles";
import type { ContentStatus } from "@/lib/types";
import { useModalFocus } from "../Drawer";
import { ChatIcon, CloseIcon, PlusIcon, SearchIcon } from "../Icons";
import { INKI, InkiIcon } from "../Inki";
import { useViewer } from "../Viewer";
import { Thread } from "./Thread";

// Conversations between a creator and the brand team, laid out like an inbox: what is waiting on you
// first, each row naming the piece it is about and where that piece stands. The list and the open thread
// stay current through one server-sent event stream; when it reconnects, the thread asks for what it
// missed by id, so a dropped stream costs a moment, never a message.

export type Listener = (e: LiveEvent | { type: "resync" }) => void;
type Tab = "all" | "unread" | "waiting";
const THINKING_MS = 60_000;
const FAILED_MS = 8_000;
// Where each piece status sits in the chips, and its dot.
const STATUS_ORDER: (ContentStatus | "none")[] = ["changes_requested", "in_review", "draft", "approved", "published",
  "withdrawn", "none"];
export const STATUS_DOT: Record<string, string> = {
  changes_requested: "bg-[var(--vt-warning)]", in_review: "bg-accent", draft: "bg-subtle",
  approved: "bg-[var(--vt-ok)]", published: "bg-[var(--vt-ok)]", withdrawn: "bg-line-strong", none: "bg-line-strong",
};
const statusOf = (c: ConversationRow) => c.topic?.status ?? "none";
const statusLabel = (s: string) => (s === "none" ? "No piece" : STATUS_LABEL[s as ContentStatus] ?? s);

export function ConversationsView() {
  const { me, side, loading } = useViewer();
  const params = useSearchParams();
  const router = useRouter();
  const [convs, setConvs] = useState<ConversationRow[] | null>(null);
  // The open conversation lives in the URL, so Back closes it on a phone and a link reopens it.
  const active = Number(params.get("c")) || null;
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [tab, setTab] = useState<Tab>("all");
  const [status, setStatus] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // Conversations where Inki was asked and hasn't answered, or couldn't. Each state clears itself, on a
  // timer per conversation, so an older ask can't clear a newer one.
  const [thinking, setThinking] = useState<Record<number, "thinking" | "failed">>({});
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const [live, setLive] = useState<"connecting" | "live" | "retrying">("connecting");
  const listeners = useRef(new Set<Listener>());
  const activeRef = useRef<number | null>(active);
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => { activeRef.current = active; }, [active]);

  // Only the newest request lands, and one that was in flight while a live message changed a row is asked
  // again, so a slow list can't put back what the stream just updated.
  const loads = useRef({ seq: 0, changedAt: 0 });
  const load = useCallback(function again(): Promise<void> {
    const seq = ++loads.current.seq;
    return listConversations().then((c) => {
      if (seq !== loads.current.seq) return;
      if (loads.current.changedAt > seq) { void again(); return; }
      setConvs(c); setError(null);
    }).catch((e: Error) => { if (seq === loads.current.seq) setError(e.message); });
  }, []);
  const convsRef = useRef<ConversationRow[] | null>(null);
  useEffect(() => { convsRef.current = convs; }, [convs]);

  const choose = useCallback((id: number | null) => {
    router.push(id ? `/conversations?c=${id}` : "/conversations", { scroll: false });
  }, [router]);

  // Deep links: ?with=<person> opens (or starts) that conversation, ?piece=<id> preselects what it is about,
  // ?c=<conversation> reopens one (read into the initial state above).
  const piece = Number(params.get("piece")) || null;
  useEffect(() => {
    const withId = Number(params.get("with")) || null;
    if (withId) {
      openConversation(withId).then((row) => {
        router.replace(`/conversations?c=${row.id}${piece ? `&piece=${piece}` : ""}`, { scroll: false });
        load();
      }).catch((e: Error) => setError(e.message));
    }
    load();
    // Read once on arrival; later choices update the URL themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // "/" jumps to search, as in most inboxes; not while typing somewhere else.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest("input, textarea, select, [contenteditable]");
      const modal = document.querySelector("[data-vt-modal]");
      if (e.key === "/" && !typing && !modal && !e.metaKey && !e.ctrlKey) { e.preventDefault(); search.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const emit: Listener = (e) => listeners.current.forEach((l) => l(e));
    const later = (id: number, ms: number) => {
      clearTimeout(timers.current.get(id));
      timers.current.set(id, setTimeout(() => {
        timers.current.delete(id);
        setThinking((t) => { const next = { ...t }; delete next[id]; return next; });
      }, ms));
    };
    const settle = (id: number) => later(id, 0);
    const connect = () => {
      source = new EventSource("/api/v/conversations/stream");
      // After a gap, anything Inki said meanwhile arrives with the reload, so no stale "reading" stays up.
      source.addEventListener("ready", () => { setLive("live"); setThinking({}); load(); emit({ type: "resync" }); });
      source.onmessage = (ev) => {
        let e: LiveEvent;
        try { e = JSON.parse(ev.data); } catch { return; }
        if (e.type === "inki") {
          const id = e.conversation_id;
          setThinking((t) => ({ ...t, [id]: e.state }));
          later(id, e.state === "failed" ? FAILED_MS : THINKING_MS);
        }
        if (e.type === "message") {
          const m = e.message;
          if (m.kind === "inki") settle(m.conversation_id);
          const row = convsRef.current?.find((c) => c.id === m.conversation_id);
          // A conversation new to this screen, or a piece whose status isn't known here: ask the server.
          if (!row || (m.piece && row.topic?.id !== m.piece.id)) void load();
          else {
            loads.current.changedAt = loads.current.seq + 1;
            setConvs((list) => list?.map((c) => c.id === m.conversation_id ? applyToRow(c, m, me?.id ?? null, activeRef.current) : c)
              .sort((a, b) => b.last_message_at.localeCompare(a.last_message_at)) ?? list);
          }
          window.dispatchEvent(new Event(CONVERSATIONS_SEEN_EVENT));
        }
        if (e.type === "read") setConvs((list) => list?.map((c) => c.id === e.conversation_id ? { ...c, unread: 0 } : c) ?? list);
        emit(e);
      };
      source.onerror = () => {
        setLive("retrying");
        // The browser retries a dropped stream by itself; a refused one (signed out, API down) it gives up on.
        if (source?.readyState === EventSource.CLOSED && !closed) retry = setTimeout(connect, 5_000);
      };
    };
    connect();
    const pending = timers.current;
    return () => { closed = true; clearTimeout(retry); source?.close(); pending.forEach(clearTimeout); pending.clear(); };
  }, [load, me?.id]);

  const subscribe = useCallback((l: Listener) => {
    listeners.current.add(l);
    return () => { listeners.current.delete(l); };
  }, []);

  const counts = useMemo(() => ({
    all: convs?.length ?? 0,
    unread: convs?.filter((c) => c.unread > 0).length ?? 0,
    waiting: convs?.filter((c) => c.needs_reply).length ?? 0,
    messages: convs?.reduce((n, c) => n + c.unread, 0) ?? 0,
  }), [convs]);
  const chips = useMemo(() => {
    const by = new Map<string, number>();
    convs?.forEach((c) => by.set(statusOf(c), (by.get(statusOf(c)) ?? 0) + 1));
    return STATUS_ORDER.filter((s) => by.has(s)).map((s) => ({ status: s, n: by.get(s)! }));
  }, [convs]);
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (convs ?? []).filter((c) => (tab === "all" || (tab === "unread" ? c.unread > 0 : c.needs_reply))
      && (!status || statusOf(c) === status)
      && (!q || [c.other.name, c.topic?.title ?? "", c.last?.text ?? ""].some((s) => s.toLowerCase().includes(q))));
  }, [convs, tab, status, query]);

  const current = convs?.find((c) => c.id === active) ?? null;
  const auditor = me?.role === "auditor";
  const filtered = tab !== "all" || status !== null || query.trim() !== "";

  return (
    <div className="flex h-[calc(100dvh-205px)] min-h-[520px] flex-col md:h-[calc(100dvh-108px)]">
      <div className="vt-card flex min-h-0 flex-1 flex-col overflow-hidden">
        {/* On a phone an open conversation takes the whole card; the filters are one tap back. */}
        <header className={`flex-col gap-3 border-b border-line px-4 pb-3 pt-4 md:flex md:px-5 ${active ? "hidden" : "flex"}`}>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
            <h1 className="flex items-baseline gap-2 text-xl font-semibold tracking-tight">
              Conversations <span className="text-sm font-normal tabular-nums text-subtle">{counts.all}</span>
            </h1>
            <div role="group" aria-label="Show" className="flex rounded-lg border border-line bg-sunken p-0.5 text-[13px]">
              {([["all", "All", counts.all], ["unread", "Unread", counts.unread], ["waiting", "Needs reply", counts.waiting]] as const)
                .map(([key, label, n]) => (
                  <button key={key} type="button" aria-pressed={tab === key} onClick={() => setTab(key)}
                    className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition ${
                      tab === key ? "bg-raised font-medium text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
                    {label}<span className="tabular-nums text-subtle">{n}</span>
                  </button>
                ))}
            </div>
            <div className="ml-auto flex min-w-0 items-center gap-2">
              <label className="relative flex min-w-0 items-center">
                <span className="sr-only">Search conversations</span>
                <SearchIcon size={14} className="pointer-events-none absolute left-2.5 text-subtle" />
                <input ref={search} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search"
                  onKeyDown={(e) => { if (e.key === "Escape") { setQuery(""); e.currentTarget.blur(); } }}
                  className="vt-input h-9 w-40 pl-8 pr-8 text-sm sm:w-56" />
                <kbd aria-hidden className="pointer-events-none absolute right-2 rounded border border-line px-1 text-[10px] text-subtle">/</kbd>
              </label>
              {!auditor && (
                <button type="button" onClick={() => setPicking(true)} className="vt-btn vt-btn-primary h-9 shrink-0">
                  <PlusIcon size={15} /><span className="hidden sm:inline">New</span>
                </button>
              )}
            </div>
          </div>
          {(chips.length > 0 || counts.all > 0) && (
            <div className="flex flex-wrap items-center gap-2">
              <div role="group" className="flex flex-wrap gap-1.5" aria-label="Filter by the piece's status">
                {chips.map(({ status: s, n }) => (
                  <button key={s} type="button" aria-pressed={status === s} onClick={() => setStatus(status === s ? null : s)}
                    className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition ${
                      status === s ? "border-accent/50 bg-accent/10 text-ink" : "border-line text-muted hover:text-ink"}`}>
                    <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[s]}`} />{statusLabel(s)}
                    <span className="tabular-nums text-subtle">{n}</span>
                  </button>
                ))}
              </div>
              <p className="ml-auto text-xs text-muted" aria-live="polite">
                <span className="font-medium tabular-nums text-ink">{counts.messages}</span> unread
                <span aria-hidden className="mx-1.5 text-subtle">·</span>
                <span className="font-medium tabular-nums text-ink">{counts.waiting}</span> waiting on you
              </p>
            </div>
          )}
        </header>

        {error && <p role="alert" className="mx-4 mt-3 rounded-xl bg-[var(--vt-blocker-bg)] px-3 py-2 text-sm text-[var(--vt-blocker)]">{error}</p>}

        <div className="flex min-h-0 flex-1">
          <aside aria-label="Conversation list" className={`min-h-0 w-full flex-col border-line md:flex md:w-[22rem] md:shrink-0 md:border-r ${active ? "hidden" : "flex"}`}>
            <ConversationList convs={convs} shown={shown} active={active} onPick={choose} meId={me?.id ?? null}
              loading={loading || convs === null} filtered={filtered}
              onClear={() => { setTab("all"); setStatus(null); setQuery(""); }} onNew={auditor ? null : () => setPicking(true)} />
            <p className="border-t border-line px-4 py-2 text-[11px] text-subtle" aria-live="polite">
              {live === "live" ? "Live: new messages appear as they are sent." : live === "connecting" ? "Connecting..." : "Reconnecting... nothing is lost."}
            </p>
          </aside>
          <section aria-label="Conversation" className={`min-h-0 min-w-0 flex-1 flex-col ${active ? "flex" : "hidden md:flex"}`}>
            {current && me ? (
              <Thread key={current.id} conv={current} me={me} side={side} subscribe={subscribe} initialPiece={piece}
                inki={thinking[current.id] ?? null} onBack={() => choose(null)}
                onRead={() => setConvs((list) => list?.map((c) => c.id === current.id ? { ...c, unread: 0 } : c) ?? list)} />
            ) : active && !convs && !error ? (
              <div aria-busy="true" aria-label="Opening the conversation" className="flex flex-1 flex-col gap-3 p-6">
                {[0, 1, 2].map((i) => <div key={i} className={`h-12 animate-pulse rounded-2xl bg-sunken ${i % 2 ? "ml-auto w-1/2" : "w-2/3"}`} />)}
              </div>
            ) : active && !convs && error ? (
              <Empty title="Conversations didn't load" body={error}
                action={<div className="flex gap-2">
                  <button type="button" onClick={() => void load()} className="vt-btn">Try again</button>
                  <button type="button" onClick={() => choose(null)} className="vt-btn vt-btn-quiet">Back to conversations</button>
                </div>} />
            ) : active && convs && !current ? (
              <Empty title="That conversation isn't here" body="It may belong to someone else, or the link is old."
                action={<button type="button" onClick={() => choose(null)} className="vt-btn vt-btn-quiet">Back to conversations</button>} />
            ) : auditor ? (
              <Empty title="Conversations are between creators and the brand team"
                body="Auditors read the record: the audit log notes when a conversation starts and when a call link is shared." />
            ) : (
              <Empty title="Pick a conversation, or start one"
                body={`Point a message at the piece it is about, share files and call links, and mention @${INKI} to ask where a piece stands.`} />
            )}
          </section>
        </div>
      </div>

      {picking && <PeoplePicker onClose={() => setPicking(false)}
        onPick={async (person) => {
          setPicking(false);
          try {
            const row = person.conversation_id ? { id: person.conversation_id } : await openConversation(person.id);
            await load();
            choose(row.id);
          } catch (e) { setError((e as Error).message); }
        }} />}
    </div>
  );
}

/** A live message applied to its row in the list: a new last message, or an edit or deletion of it. */
function applyToRow(c: ConversationRow, m: ChatMessage, meId: number | null, activeId: number | null): ConversationRow {
  const isNew = !c.last || m.id > c.last.id;
  // An edit or a deletion of the last message: its words change, and a deleted one waits on nobody.
  if (!isNew) return c.last?.id === m.id ? { ...c, last: m, needs_reply: m.deleted ? false : c.needs_reply } : c;
  // Counted the way the server counts: anything not written by me, Inki's answers to me included.
  const mine = m.sender !== null && m.sender.id === meId;
  const fromOther = m.sender?.id === c.other.id || (m.sender === null && m.asked_by?.id === c.other.id);
  return { ...c, last: m, last_message_at: m.created_at, needs_reply: fromOther,
    unread: mine || activeId === c.id ? c.unread : c.unread + 1 };
}

export function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";
}

export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  return (
    <span aria-hidden style={{ width: size, height: size }}
      className="grid shrink-0 place-items-center rounded-full bg-accent/12 text-xs font-semibold text-accent">{initials(name)}</span>
  );
}

export function preview(m: ChatMessage | null, meId: number | null): string {
  if (!m) return "No messages yet";
  if (m.deleted) return "Message deleted";
  const who = m.sender === null ? `${INKI}: ` : m.sender.id === meId ? "You: " : "";
  if (m.text) return who + m.text.replace(/\s+/g, " ");
  if (m.call) return `${who}shared a ${m.call.provider} link`;
  if (m.files.length) return `${who}shared ${m.files.length === 1 ? m.files[0].name : `${m.files.length} files`}`;
  return who.trim();
}

function ConversationList({ convs, shown, active, onPick, meId, loading, filtered, onClear, onNew }: {
  convs: ConversationRow[] | null; shown: ConversationRow[]; active: number | null; onPick: (id: number) => void;
  meId: number | null; loading: boolean; filtered: boolean; onClear: () => void; onNew: (() => void) | null;
}) {
  if (loading && !convs) {
    return <div className="flex-1 space-y-2 p-3">{[0, 1, 2, 3].map((i) => <div key={i} className="h-[4.5rem] animate-pulse rounded-lg bg-sunken" />)}</div>;
  }
  if (!convs?.length || !shown.length) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
        <ChatIcon size={22} className="text-subtle" />
        <p className="text-sm font-medium">{convs?.length ? "Nothing matches" : "No conversations yet"}</p>
        {convs?.length && filtered ? (
          <button type="button" onClick={onClear} className="vt-btn vt-btn-quiet text-xs">Show all</button>
        ) : onNew ? (
          <button type="button" onClick={onNew} className="vt-btn vt-btn-quiet text-xs"><PlusIcon size={13} /> Start one</button>
        ) : null}
      </div>
    );
  }
  return (
    <ul className="min-h-0 flex-1 overflow-y-auto p-2">
      {shown.map((c) => {
        const status = statusOf(c);
        return (
          <li key={c.id}>
            <button type="button" onClick={() => onPick(c.id)} aria-current={c.id === active ? "true" : undefined}
              className={`flex w-full gap-3 rounded-lg px-2.5 py-2.5 text-left transition ${c.id === active ? "bg-accent/10" : "hover:bg-sunken"}`}>
              <Avatar name={c.other.name} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  {c.unread > 0 && <span aria-label="Unread" className="mb-0.5 h-1.5 w-1.5 shrink-0 self-center rounded-full bg-accent" />}
                  <span className={`truncate text-sm ${c.unread ? "font-semibold" : "font-medium"}`}>{c.other.name}</span>
                  <span className="shrink-0 truncate text-xs text-subtle">{ROLE_LABEL[c.other.role] ?? c.other.role}</span>
                  <span className="ml-auto shrink-0 pl-2 text-[11px] text-subtle">{relativeTime(c.last?.created_at ?? c.last_message_at)}</span>
                </span>
                <span className="mt-0.5 block truncate text-[13px] font-medium">{c.topic?.title ?? "General"}</span>
                <span className="mt-0.5 flex items-center gap-2">
                  <span className={`min-w-0 flex-1 truncate text-[13px] ${c.unread ? "text-ink" : "text-muted"}`}>{preview(c.last, meId)}</span>
                  {c.needs_reply ? (
                    <span className="shrink-0 rounded-full bg-accent/12 px-1.5 text-[11px] font-medium text-accent">Your turn</span>
                  ) : status !== "none" && (
                    <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted">
                      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[status]}`} />{statusLabel(status)}
                    </span>
                  )}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function Empty({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
      <InkiIcon size={44} />
      <p className="text-base font-semibold">{title}</p>
      <p className="max-w-md text-sm leading-6 text-muted">{body}</p>
      {action}
    </div>
  );
}

function PeoplePicker({ onClose, onPick }: { onClose: () => void; onPick: (p: Contact) => void }) {
  const [people, setPeople] = useState<Contact[] | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  // Focus stays inside while it is open and goes back where it was after; Escape closes it.
  useModalFocus(panel, onClose);
  useEffect(() => { listContacts().then(setPeople).catch((e: Error) => setError(e.message)); }, []);
  const shown = people?.filter((p) => p.name.toLowerCase().includes(q.trim().toLowerCase())) ?? [];
  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4">
      <div aria-hidden onClick={onClose} className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]" />
      <div ref={panel} role="dialog" aria-modal="true" aria-label="New conversation"
        className="vt-pop relative flex max-h-[min(32rem,calc(100dvh-2rem))] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-base font-semibold">New conversation</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-sunken hover:text-ink"><CloseIcon size={16} /></button>
        </div>
        <div className="px-4 pt-3">
          <input data-autofocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name" aria-label="Search people" className="vt-input w-full text-sm" />
        </div>
        <ul className="min-h-0 flex-1 overflow-y-auto p-2">
          {error && <li role="alert" className="px-2 py-3 text-sm text-[var(--vt-blocker)]">{error}</li>}
          {people === null && !error && <li className="px-2 py-3 text-sm text-muted">Loading people...</li>}
          {people?.length === 0 && <li className="px-2 py-3 text-sm text-muted">There is no one to talk to in this workspace yet.</li>}
          {people && people.length > 0 && shown.length === 0 && <li className="px-2 py-3 text-sm text-muted">No one by that name.</li>}
          {shown.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onPick(p)} className="flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-sunken">
                <Avatar name={p.name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{p.name}</span>
                  <span className="block text-xs text-subtle">{ROLE_LABEL[p.role] ?? p.role}</span>
                </span>
                {p.conversation_id && <span className="text-[11px] text-subtle">Open</span>}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>,
    document.body,
  );
}

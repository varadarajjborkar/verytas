"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CALL_STARTERS, type ChatMessage, type Contact, type ConversationRow, type LiveEvent, MESSAGES_SEEN_EVENT,
  listContacts, listConversations, listMessages, markRead, newClientId, openConversation, sendMessage,
} from "@/lib/messages-client";
import { ApiError, listContents, relativeTime } from "@/lib/review-client";
import { ROLE_LABEL } from "@/lib/roles";
import type { ContentRow } from "@/lib/types";
import { ArrowUpIcon, ChatIcon, CloseIcon, PlusIcon, ReviewIcon, ShieldIcon, VideoIcon } from "../Icons";
import { INKI, InkiIcon } from "../Inki";
import { useViewer } from "../Viewer";

// Conversations between a creator and the brand team. The list and the open thread stay current through
// one server-sent event stream; when it reconnects, the thread asks for what it missed by id, so a dropped
// stream costs a moment, never a message. Calls are links to the company's own meeting service.

type Listener = (e: LiveEvent | { type: "resync" }) => void;
const THINKING_MS = 60_000;
const PAGE = 30;

export function MessagesView() {
  const { me, side, loading } = useViewer();
  const params = useSearchParams();
  const router = useRouter();
  const [convs, setConvs] = useState<ConversationRow[] | null>(null);
  const [active, setActive] = useState<number | null>(() => Number(params.get("c")) || null);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  // Conversations where Inki was asked and hasn't answered yet; each clears itself if no answer comes.
  const [thinking, setThinking] = useState<Record<number, boolean>>({});
  const [live, setLive] = useState<"connecting" | "live" | "retrying">("connecting");
  const listeners = useRef(new Set<Listener>());
  const activeRef = useRef<number | null>(active);
  useEffect(() => { activeRef.current = active; }, [active]);

  const load = useCallback(() => listConversations().then((c) => { setConvs(c); setError(null); })
    .catch((e: Error) => setError(e.message)), []);

  const choose = useCallback((id: number | null) => {
    setActive(id);
    router.replace(id ? `/messages?c=${id}` : "/messages", { scroll: false });
  }, [router]);

  // Deep links: ?with=<person> opens (or starts) that conversation, ?piece=<id> preselects what it is about,
  // ?c=<conversation> reopens one (read into the initial state above).
  const piece = Number(params.get("piece")) || null;
  useEffect(() => {
    const withId = Number(params.get("with")) || null;
    if (withId) {
      openConversation(withId).then((row) => { setActive(row.id); load(); }).catch((e: Error) => setError(e.message));
    }
    load();
    // Read once on arrival; later choices update the URL themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const emit: Listener = (e) => listeners.current.forEach((l) => l(e));
    const connect = () => {
      source = new EventSource("/api/v/conversations/stream");
      source.addEventListener("ready", () => { setLive("live"); load(); emit({ type: "resync" }); });
      source.onmessage = (ev) => {
        let e: LiveEvent;
        try { e = JSON.parse(ev.data); } catch { return; }
        const settle = (id: number) => setThinking((t) => { const next = { ...t }; delete next[id]; return next; });
        if (e.type === "inki" && e.state === "failed") settle(e.conversation_id);
        if (e.type === "inki" && e.state === "thinking") {
          const id = e.conversation_id;
          setThinking((t) => ({ ...t, [id]: true }));
          setTimeout(() => settle(id), THINKING_MS);
        }
        if (e.type === "message") {
          const m = e.message;
          if (m.kind === "inki") settle(m.conversation_id);
          setConvs((list) => {
            if (!list?.some((c) => c.id === m.conversation_id)) { load(); return list; }
            const mine = m.sender?.id === me?.id;
            const seen = mine || activeRef.current === m.conversation_id;
            return list.map((c) => c.id === m.conversation_id
              ? { ...c, last: m, last_message_at: m.created_at, unread: seen ? c.unread : c.unread + 1 } : c)
              .sort((a, b) => b.last_message_at.localeCompare(a.last_message_at));
          });
        }
        if (e.type === "read") setConvs((list) => list?.map((c) => c.id === e.conversation_id ? { ...c, unread: 0 } : c) ?? list);
        emit(e);
      };
      source.onerror = () => {
        setLive("retrying");
        // The browser retries a dropped stream by itself; a refused one (signed out, API down) it gives up on.
        if (source?.readyState === EventSource.CLOSED && !closed) {
          retry = setTimeout(connect, 5_000);
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(retry); source?.close(); };
  }, [load, me?.id]);

  const subscribe = useCallback((l: Listener) => {
    listeners.current.add(l);
    return () => { listeners.current.delete(l); };
  }, []);

  const current = convs?.find((c) => c.id === active) ?? null;
  const auditor = me?.role === "auditor";

  return (
    <div className="flex h-[calc(100dvh-205px)] min-h-[480px] flex-col md:h-[calc(100dvh-108px)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[1.65rem] font-semibold leading-tight tracking-tight">Messages</h1>
          <p className="mt-1 text-sm text-muted">
            {side === "creator" ? "Talk a piece through with the brand team." : "Talk a piece through with the creator who wrote it."}{" "}
            Mention <span className="font-medium text-ink">@{INKI}</span> to bring in the assistant.
          </p>
        </div>
        {!auditor && (
          <button type="button" onClick={() => setPicking(true)} className="vt-btn vt-btn-primary"><PlusIcon size={15} /> New conversation</button>
        )}
      </div>

      {error && <p role="alert" className="mb-3 rounded-xl bg-[var(--vt-blocker-bg)] px-3 py-2 text-sm text-[var(--vt-blocker)]">{error}</p>}

      <div className="vt-card flex min-h-0 flex-1 overflow-hidden">
        <aside aria-label="Conversations" className={`min-h-0 w-full flex-col border-line md:flex md:w-80 md:shrink-0 md:border-r ${active ? "hidden" : "flex"}`}>
          <ConversationList convs={convs} active={active} onPick={choose} meId={me?.id ?? null} loading={loading || convs === null} />
          <p className="border-t border-line px-4 py-2 text-[11px] text-subtle" aria-live="polite">
            {live === "live" ? "Live: new messages appear as they are sent." : live === "connecting" ? "Connecting..." : "Reconnecting... messages are kept and will appear."}
          </p>
        </aside>
        <section aria-label="Conversation" className={`min-h-0 min-w-0 flex-1 flex-col ${active ? "flex" : "hidden md:flex"}`}>
          {current && me ? (
            <Thread key={current.id} conv={current} meId={me.id} side={side} subscribe={subscribe} initialPiece={piece}
              thinking={Boolean(thinking[current.id])} onBack={() => choose(null)}
              onRead={() => setConvs((list) => list?.map((c) => c.id === current.id ? { ...c, unread: 0 } : c) ?? list)} />
          ) : active && convs && !current ? (
            <Empty title="That conversation isn't here" body="It may belong to someone else, or the link is old." />
          ) : auditor ? (
            <Empty title="Conversations are between creators and the brand team" body="Auditors read the record; the audit log notes when a conversation starts and when a call link is shared." />
          ) : (
            <Empty title="Pick a conversation, or start one"
              body={`Point a message at the piece it is about, mention @${INKI} to ask where it stands, and share a Google Meet, Teams or Zoom link when it is easier to talk. Personal phone numbers are kept out of the conversation.`} />
          )}
        </section>
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

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";
}

function Avatar({ name }: { name: string }) {
  return <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent/12 text-xs font-semibold text-accent">{initials(name)}</span>;
}

function preview(m: ChatMessage | null, meId: number | null): string {
  if (!m) return "No messages yet";
  const who = m.sender === null ? `${INKI}: ` : m.sender.id === meId ? "You: " : "";
  if (m.kind === "call" && !m.text) return `${who}shared a ${m.call?.provider ?? "call"} link`;
  return who + m.text.replace(/\s+/g, " ");
}

function ConversationList({ convs, active, onPick, meId, loading }: {
  convs: ConversationRow[] | null; active: number | null; onPick: (id: number) => void; meId: number | null; loading: boolean;
}) {
  if (loading && !convs) {
    return <div className="flex-1 space-y-2 p-3">{[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-lg bg-sunken" />)}</div>;
  }
  if (!convs?.length) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
        <ChatIcon size={22} className="text-subtle" />
        <p className="text-sm font-medium">No conversations yet</p>
        <p className="text-[13px] text-muted">Press &quot;New conversation&quot; to message someone.</p>
      </div>
    );
  }
  return (
    <ul className="min-h-0 flex-1 overflow-y-auto p-2">
      {convs.map((c) => (
        <li key={c.id}>
          <button type="button" onClick={() => onPick(c.id)} aria-current={c.id === active ? "true" : undefined}
            className={`flex w-full items-center gap-3 rounded-lg px-2.5 py-2.5 text-left transition ${c.id === active ? "bg-accent/10" : "hover:bg-sunken"}`}>
            <Avatar name={c.other.name} />
            <span className="min-w-0 flex-1">
              <span className="flex items-baseline justify-between gap-2">
                <span className="truncate text-sm font-medium">{c.other.name}</span>
                <span className="shrink-0 text-[11px] text-subtle">{relativeTime(c.last?.created_at ?? null)}</span>
              </span>
              <span className="flex items-center justify-between gap-2">
                <span className={`truncate text-[13px] ${c.unread ? "font-medium text-ink" : "text-muted"}`}>{preview(c.last, meId)}</span>
                {c.unread > 0 && (
                  <span aria-label={`${c.unread} unread`} className="shrink-0 rounded-full bg-accent px-1.5 text-[11px] font-semibold tabular-nums text-accent-ink">{c.unread}</span>
                )}
              </span>
              <span className="block text-[11px] text-subtle">{ROLE_LABEL[c.other.role] ?? c.other.role}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-8 text-center">
      <InkiIcon size={44} />
      <p className="text-base font-semibold">{title}</p>
      <p className="max-w-md text-sm leading-6 text-muted">{body}</p>
    </div>
  );
}

function Thread({ conv, meId, side, subscribe, thinking, initialPiece, onBack, onRead }: {
  conv: ConversationRow; meId: number; side: "creator" | "manager"; subscribe: (l: Listener) => () => void;
  thinking: boolean; initialPiece: number | null; onBack: () => void; onRead: () => void;
}) {
  const [msgs, setMsgs] = useState<ChatMessage[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const marked = useRef(0);

  const merge = useCallback((incoming: ChatMessage[]) => setMsgs((list) => {
    const byId = new Map((list ?? []).map((m) => [m.id, m]));
    incoming.forEach((m) => byId.set(m.id, m));
    return [...byId.values()].sort((a, b) => a.id - b.id);
  }), []);

  useEffect(() => {
    listMessages(conv.id).then((m) => { setMsgs(m); setMore(m.length >= PAGE); }).catch((e: Error) => setError(e.message));
  }, [conv.id]);

  const lastId = msgs?.at(-1)?.id ?? 0;
  const lastRef = useRef(0);
  useEffect(() => { lastRef.current = lastId; }, [lastId]);
  useEffect(() => subscribe((e) => {
    if (e.type === "message" && e.message.conversation_id === conv.id) merge([e.message]);
    if (e.type === "resync") listMessages(conv.id, { after: lastRef.current }).then(merge).catch(() => {});
  }), [conv.id, merge, subscribe]);

  // Follow new messages while the reader is at the bottom; leave them be while they read further up.
  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [msgs, thinking]);

  // Seen once shown in a visible tab; the nav badge is told to look again.
  useEffect(() => {
    if (!lastId || lastId <= marked.current) return;
    const mark = () => {
      if (document.hidden || lastId <= marked.current) return;
      marked.current = lastId;
      markRead(conv.id, lastId).then(() => { onRead(); window.dispatchEvent(new Event(MESSAGES_SEEN_EVENT)); }).catch(() => {});
    };
    mark();
    document.addEventListener("visibilitychange", mark);
    return () => document.removeEventListener("visibilitychange", mark);
  }, [conv.id, lastId, onRead]);

  const loadOlder = async () => {
    const first = msgs?.[0]?.id;
    if (!first) return;
    const el = scroller.current;
    const from = el ? el.scrollHeight - el.scrollTop : 0;
    const older = await listMessages(conv.id, { before: first }).catch(() => []);
    setMore(older.length >= PAGE);
    stick.current = false;
    merge(older);
    requestAnimationFrame(() => { if (el) el.scrollTop = el.scrollHeight - from; });
  };

  return (
    <>
      <header className="flex items-center gap-3 border-b border-line px-4 py-3">
        <button type="button" onClick={onBack} aria-label="Back to conversations" className="vt-btn vt-btn-quiet px-2.5 md:hidden">&larr;</button>
        <Avatar name={conv.other.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{conv.other.name}</p>
          <p className="text-xs text-subtle">{ROLE_LABEL[conv.other.role] ?? conv.other.role}</p>
        </div>
      </header>
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
        onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}>
        {error && <p role="alert" className="text-sm text-[var(--vt-blocker)]">{error}</p>}
        {msgs === null && !error && <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-10 w-2/3 animate-pulse rounded-2xl bg-sunken" />)}</div>}
        {more && <div className="mb-3 text-center"><button type="button" onClick={loadOlder} className="vt-btn vt-btn-quiet text-xs">Show earlier messages</button></div>}
        {msgs?.length === 0 && (
          <div className="mx-auto mt-8 max-w-sm text-center text-sm text-muted">
            <p className="font-medium text-ink">Say hello to {conv.other.name.split(" ")[0]}</p>
            <p className="mt-1">Pick the piece this is about under the box, so you both, and @{INKI}, know what you mean.</p>
          </div>
        )}
        <ol className="flex flex-col gap-3">
          {msgs?.map((m) => <Bubble key={m.id} m={m} mine={m.sender?.id === meId} side={side} />)}
          {thinking && (
            <li className="flex items-center gap-2 text-[13px] text-muted" aria-live="polite">
              <InkiIcon size={22} /> {INKI} is reading the conversation
              <span className="vt-typing inline-flex gap-1"><span className="h-1.5 w-1.5 rounded-full bg-subtle" /><span className="h-1.5 w-1.5 rounded-full bg-subtle" /><span className="h-1.5 w-1.5 rounded-full bg-subtle" /></span>
            </li>
          )}
        </ol>
      </div>
      <Composer conv={conv} side={side} initialPiece={initialPiece}
        onSent={(m) => { stick.current = true; merge([m]); }} />
    </>
  );
}

function pieceHref(side: "creator" | "manager", id: number) {
  return side === "creator" ? `/review?id=${id}` : `/review?queue=all&id=${id}`;
}

function Bubble({ m, mine, side }: { m: ChatMessage; mine: boolean; side: "creator" | "manager" }) {
  const time = new Date(m.created_at);
  const stamp = <time dateTime={m.created_at} title={time.toLocaleString()} className="text-[11px] text-subtle">
    {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>;
  const piece = m.piece && (
    <Link href={pieceHref(side, m.piece.id)} className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line bg-raised px-2.5 py-0.5 text-xs text-muted hover:text-accent">
      <ReviewIcon size={12} className="shrink-0" /><span className="truncate">About: {m.piece.title}</span>
    </Link>
  );
  if (m.kind === "inki") {
    return (
      <li className="vt-pop flex gap-2.5">
        <InkiIcon size={28} className="mt-0.5" />
        <div className="min-w-0 max-w-[85%] rounded-2xl rounded-tl-md border border-accent/25 bg-accent/[0.06] px-3.5 py-2.5">
          <p className="mb-1 text-xs font-medium text-accent">{INKI}{m.asked_by ? <span className="font-normal text-subtle"> · answering {m.asked_by.name}</span> : null}</p>
          <p className="whitespace-pre-wrap text-sm leading-6 [overflow-wrap:anywhere]">{m.text}</p>
          <p className="mt-1.5 flex flex-wrap items-center gap-2">{piece}{stamp}<span className="text-[11px] text-subtle">AI-written; the brand team decides.</span></p>
        </div>
      </li>
    );
  }
  return (
    <li className={`vt-pop flex flex-col gap-1 ${mine ? "items-end" : "items-start"}`}>
      {!mine && m.sender && <span className="px-1 text-[11px] text-subtle">{m.sender.name}</span>}
      {m.call && (
        <div className="flex w-72 max-w-full items-center gap-3 rounded-2xl border border-line bg-raised px-3.5 py-3">
          <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent"><VideoIcon size={16} /></span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">{m.call.provider} call</span>
            <span className="block text-[11px] text-subtle">{mine ? "You shared a meeting link" : `${m.sender?.name ?? "They"} shared a meeting link`}</span>
          </span>
          <a href={m.call.url} target="_blank" rel="noopener noreferrer" className="vt-btn vt-btn-primary shrink-0 text-xs">Join</a>
        </div>
      )}
      {m.text && (
        <p className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-6 [overflow-wrap:anywhere] ${
          mine ? "rounded-br-md bg-accent text-accent-ink" : "rounded-bl-md bg-sunken"}`}>
          <Mentions text={m.text} mine={mine} />
        </p>
      )}
      <span className="flex flex-wrap items-center gap-2 px-1">{piece}{stamp}</span>
    </li>
  );
}

function Mentions({ text, mine }: { text: string; mine: boolean }) {
  const parts = text.split(/(@inki\b)/i);
  return <>{parts.map((p, i) => /^@inki$/i.test(p)
    ? <span key={i} className={`rounded px-0.5 font-semibold ${mine ? "bg-white/20" : "bg-accent/12 text-accent"}`}>{p}</span>
    : p)}</>;
}

function Composer({ conv, side, initialPiece, onSent }: {
  conv: ConversationRow; side: "creator" | "manager"; initialPiece: number | null; onSent: (m: ChatMessage) => void;
}) {
  const [text, setText] = useState("");
  const [piece, setPiece] = useState<number | null>(initialPiece);
  const [pieces, setPieces] = useState<ContentRow[] | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [calling, setCalling] = useState(false);
  const [link, setLink] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  // One id per message being sent: a retry of the same message reuses it, so it is stored once.
  const pending = useRef<string | null>(null);

  useEffect(() => {
    const creatorId = side === "creator" ? null : conv.other.id;
    listContents(side === "creator")
      .then((rows) => setPieces(rows.filter((r) => creatorId === null || r.created_by === creatorId)))
      .catch(() => setPieces([]));
  }, [conv.other.id, side]);

  const mention = useMemo(() => {
    const m = /(^|\s)@(\w*)$/.exec(text);
    return m && INKI.toLowerCase().startsWith(m[2].toLowerCase()) && m[2].toLowerCase() !== INKI.toLowerCase();
  }, [text]);

  const takeMention = () => {
    setText((t) => t.replace(/@(\w*)$/, `@${INKI} `));
    box.current?.focus();
  };

  const send = async (body: { text?: string; call_url?: string }) => {
    if (sending) return;
    setSending(true);
    setError(null);
    pending.current ??= newClientId();
    try {
      const m = await sendMessage(conv.id, { ...body, content_id: piece, client_id: pending.current });
      pending.current = null;
      onSent(m);
      return true;
    } catch (e) {
      // Refused (a personal number, a link from an unknown service): a new attempt is a new message.
      if (e instanceof ApiError && e.status < 500) pending.current = null;
      setError(e instanceof ApiError ? e.message : "Couldn't send. Check your connection and try again.");
      return false;
    } finally {
      setSending(false);
    }
  };

  const submit = async () => {
    const t = text.trim();
    if (!t) return;
    if (await send({ text: t })) { setText(""); }
  };

  const shareCall = async () => {
    const url = link.trim();
    if (!url) return;
    if (await send({ call_url: url })) { setLink(""); setCalling(false); }
  };

  return (
    <div className="border-t border-line px-3 py-3 md:px-4">
      {error && <p role="alert" className="mb-2 rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-1.5 text-[13px] text-[var(--vt-blocker)]">{error}</p>}
      {calling && (
        <div className="mb-2 rounded-xl border border-line bg-surface p-3">
          <div className="flex items-start justify-between gap-2">
            <p className="text-[13px] font-medium">Share a call link</p>
            <button type="button" onClick={() => setCalling(false)} aria-label="Close" className="grid h-6 w-6 place-items-center rounded text-muted hover:text-ink"><CloseIcon size={13} /></button>
          </div>
          <p className="mt-0.5 text-xs text-muted">Start a meeting where your company already meets, copy its link and paste it here. Nobody&apos;s phone number is shared.</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {CALL_STARTERS.map((s) => (
              <a key={s.name} href={s.start} target="_blank" rel="noopener noreferrer" className="vt-btn vt-btn-quiet text-xs">New {s.name}</a>
            ))}
          </div>
          <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); void shareCall(); }}>
            <label className="sr-only" htmlFor={`call-${conv.id}`}>Meeting link</label>
            <input id={`call-${conv.id}`} value={link} onChange={(e) => setLink(e.target.value)} inputMode="url"
              placeholder="https://meet.google.com/abc-defg-hij" className="vt-input min-w-0 flex-1 text-sm" />
            <button type="submit" disabled={!link.trim() || sending} className="vt-btn vt-btn-primary text-sm">Share</button>
          </form>
        </div>
      )}
      {mention && (
        <button type="button" onClick={takeMention} className="mb-2 flex items-center gap-2 rounded-lg border border-line bg-raised px-3 py-1.5 text-left text-[13px] shadow-sm hover:border-accent/40">
          <InkiIcon size={20} /><span><span className="font-medium">@{INKI}</span> <span className="text-muted">asks the assistant, using this conversation and the linked piece</span></span>
          <kbd className="ml-auto rounded border border-line px-1 text-[10px] text-subtle">Tab</kbd>
        </button>
      )}
      <div className="flex items-end gap-2">
        <label className="sr-only" htmlFor={`msg-${conv.id}`}>Message</label>
        <textarea id={`msg-${conv.id}`} ref={box} value={text} rows={1} maxLength={4000}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (mention && (e.key === "Tab" || e.key === "Enter")) { e.preventDefault(); takeMention(); return; }
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); }
          }}
          placeholder={`Message ${conv.other.name.split(" ")[0]}, or ask @${INKI}`}
          className="vt-input max-h-40 min-h-[42px] flex-1 resize-none py-2.5 text-sm [field-sizing:content]" />
        <button type="button" onClick={() => void submit()} disabled={!text.trim() || sending} aria-label="Send"
          className="vt-btn vt-btn-primary h-[42px] w-[42px] shrink-0 justify-center p-0"><ArrowUpIcon size={16} /></button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <label className="flex min-w-0 items-center gap-1.5 text-xs text-muted">
          <span className="shrink-0">About</span>
          <select value={piece ?? ""} onChange={(e) => setPiece(e.target.value ? Number(e.target.value) : null)}
            className="vt-input h-8 min-w-0 max-w-[16rem] truncate py-0 text-xs">
            <option value="">No piece</option>
            {pieces?.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            {piece && pieces && !pieces.some((p) => p.id === piece) && <option value={piece}>Piece #{piece}</option>}
          </select>
        </label>
        <button type="button" onClick={() => { setText((t) => (t.trim() ? `${t.trimEnd()} @${INKI} ` : `@${INKI} `)); box.current?.focus(); }}
          className="vt-btn vt-btn-quiet h-8 text-xs"><InkiIcon size={16} /> Ask {INKI}</button>
        <button type="button" onClick={() => setCalling((c) => !c)} aria-expanded={calling} className="vt-btn vt-btn-quiet h-8 text-xs">
          <VideoIcon size={14} /> Call
        </button>
        <span className="ml-auto hidden items-center gap-1 text-[11px] text-subtle sm:flex"><ShieldIcon size={12} /> Encrypted at rest. Personal numbers are kept out.</span>
      </div>
    </div>
  );
}

function PeoplePicker({ onClose, onPick }: { onClose: () => void; onPick: (p: Contact) => void }) {
  const [people, setPeople] = useState<Contact[] | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { listContacts().then(setPeople).catch((e: Error) => setError(e.message)); }, []);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const shown = people?.filter((p) => p.name.toLowerCase().includes(q.trim().toLowerCase())) ?? [];
  return (
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4">
      <div aria-hidden onClick={onClose} className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]" />
      <div role="dialog" aria-modal="true" aria-label="New conversation"
        className="vt-pop relative flex max-h-[min(32rem,calc(100dvh-2rem))] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <h2 className="text-base font-semibold">New conversation</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-sunken hover:text-ink"><CloseIcon size={16} /></button>
        </div>
        <div className="px-4 pt-3">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name" aria-label="Search people" className="vt-input w-full text-sm" />
        </div>
        <ul className="min-h-0 flex-1 overflow-y-auto p-2">
          {error && <li role="alert" className="px-2 py-3 text-sm text-[var(--vt-blocker)]">{error}</li>}
          {people === null && !error && <li className="px-2 py-3 text-sm text-muted">Loading people...</li>}
          {people?.length === 0 && <li className="px-2 py-3 text-sm text-muted">There is no one to message in this workspace yet.</li>}
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
    </div>
  );
}

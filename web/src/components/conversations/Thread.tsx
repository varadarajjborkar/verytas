"use client";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ACCEPT, type ChatMessage, CONVERSATIONS_SEEN_EVENT, type ConversationRow, MAX_FILES,
  type SharedFile, acceptInki, deleteMessage, editMessage, fileUrl, listMessages, markRead, needsInkiConsent,
  newClientId, posterUrl, sendMessage, withdrawInki, inkiConsent,
} from "@/lib/conversations-client";
import { ApiError, listContents, STATUS_LABEL, upload } from "@/lib/review-client";
import { ROLE_LABEL } from "@/lib/roles";
import type { ContentRow, ContentStatus, Me } from "@/lib/types";
import { useModalFocus } from "../Drawer";
import {
  ArrowUpIcon, CloseIcon, ExternalIcon, FileIcon, PaperclipIcon, PencilIcon, ReplyIcon, ShieldIcon, TrashIcon,
  VideoIcon,
} from "../Icons";
import { INKI, InkiIcon } from "../Inki";
import { Avatar, type Listener, STATUS_DOT } from "./ConversationsView";

const PAGE = 30;
// Questions Inki can take from the card above the box; each is sent as an ordinary "@Inki" message.
const ASK_INKI = ["What is still open on this piece?", "Summarise this conversation", "Draft a reply for me"];

type Pending = { key: string; name: string; state: "uploading" | "ready" | "failed"; file?: SharedFile; error?: string };

function pieceHref(side: "creator" | "manager", id: number) {
  return side === "creator" ? `/review?id=${id}` : `/review?queue=all&id=${id}`;
}

function size(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function Thread({ conv, me, side, subscribe, inki, initialPiece, onBack, onRead }: {
  conv: ConversationRow; me: Me; side: "creator" | "manager"; subscribe: (l: Listener) => () => void;
  inki: "thinking" | "failed" | null; initialPiece: number | null; onBack: () => void; onRead: () => void;
}) {
  const thinking = inki === "thinking";
  const [msgs, setMsgs] = useState<ChatMessage[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [editing, setEditing] = useState<ChatMessage | null>(null);
  const [viewing, setViewing] = useState<SharedFile | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const marked = useRef(0);
  const marking = useRef(0);
  const lastRef = useRef(0);

  const merge = useCallback((incoming: ChatMessage[]) => setMsgs((list) => {
    const byId = new Map((list ?? []).map((m) => [m.id, m]));
    // A message only moves forward: plain, then edited, then deleted. A slow page fetched before a live
    // edit or deletion arrived must not put the older copy back.
    const stage = (m: ChatMessage) => (m.deleted ? 2 : m.edited ? 1 : 0);
    incoming.forEach((m) => { const had = byId.get(m.id); if (!had || stage(m) >= stage(had)) byId.set(m.id, m); });
    return [...byId.values()].sort((a, b) => a.id - b.id);
  }), []);

  useEffect(() => {
    // Merged, not replaced: a live message that lands while this loads must not be dropped.
    listMessages(conv.id).then((m) => { merge(m); setMore(m.length >= PAGE); }).catch((e: Error) => setError(e.message));
  }, [conv.id, merge]);

  // Everything after the last message seen, page by page, so a long gap leaves no hole in the middle.
  // With nothing loaded yet there is no "after": the newest page is the whole answer.
  const catchUp = useCallback(async () => {
    try {
      let after = lastRef.current;
      for (let page = 0; after && page < 20; page++) {
        const got = await listMessages(conv.id, { after });
        merge(got);
        if (got.length < PAGE) break;
        after = got.at(-1)!.id;
      }
      merge(await listMessages(conv.id));
    } catch { /* the next reconnect tries again */ }
  }, [conv.id, merge]);

  const lastId = msgs?.at(-1)?.id ?? 0;
  useEffect(() => { lastRef.current = lastId; }, [lastId]);
  useEffect(() => subscribe((e) => {
    if (e.type === "message" && e.message.conversation_id === conv.id) merge([e.message]);
    // After a gap: what is new since the last id, and the newest page again, which carries any edits and
    // deletions made while the stream was down.
    if (e.type === "resync") void catchUp();
  }), [conv.id, merge, subscribe, catchUp]);

  // Follow new messages while the reader is at the bottom; leave them be while they read further up. Pictures
  // and videos load after the text, so the content's growth is watched too.
  const content = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [msgs, thinking]);
  useEffect(() => {
    const el = scroller.current;
    if (!el || !content.current) return;
    const watch = new ResizeObserver(() => { if (stick.current) el.scrollTop = el.scrollHeight; });
    watch.observe(content.current);
    return () => watch.disconnect();
  }, []);

  // Seen once shown in a visible tab; the nav badge is told to look again.
  useEffect(() => {
    if (!lastId || lastId <= marked.current) return;
    const mark = () => {
      if (document.hidden || lastId <= marked.current || marking.current >= lastId) return;
      // Counted as read only once the server has it; a failed call is tried again on the next look.
      marking.current = lastId;
      markRead(conv.id, lastId)
        .then(() => { marked.current = Math.max(marked.current, lastId); onRead(); window.dispatchEvent(new Event(CONVERSATIONS_SEEN_EVENT)); })
        .catch(() => {})
        .finally(() => { if (marking.current === lastId) marking.current = 0; });
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
    let older: ChatMessage[];
    try {
      older = await listMessages(conv.id, { before: first });
    } catch (e) {
      setError(`Earlier messages didn't load (${(e as Error).message}). Try again.`);
      return;
    }
    setMore(older.length >= PAGE);
    stick.current = false;
    merge(older);
    requestAnimationFrame(() => { if (el) el.scrollTop = el.scrollHeight - from; });
  };

  const remove = async (m: ChatMessage) => {
    if (!window.confirm("Delete this message for everyone? Its files go too.")) return;
    try { merge([await deleteMessage(conv.id, m.id)]); } catch (e) { setError((e as Error).message); }
  };

  const jump = async (id: number) => {
    let el = scroller.current?.querySelector<HTMLElement>(`[data-message="${id}"]`);
    // The quoted message may be on an earlier page: load back to it (a few pages at most), then show it.
    let first = msgs?.[0]?.id;
    for (let page = 0; !el && first && id < first && page < 10; page++) {
      let older: ChatMessage[];
      try { older = await listMessages(conv.id, { before: first }); } catch { break; }
      if (!older.length) break;
      stick.current = false;
      merge(older);
      setMore(older.length >= PAGE);
      first = older[0].id;
      await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      el = scroller.current?.querySelector<HTMLElement>(`[data-message="${id}"]`);
    }
    if (!el) { setError("That message is no longer in this conversation."); return; }
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("vt-flash");
    setTimeout(() => el.classList.remove("vt-flash"), 1200);
  };

  const status = conv.topic?.status;
  return (
    <>
      <header className="flex items-center gap-3 border-b border-line px-4 py-3 md:px-5">
        <button type="button" onClick={onBack} aria-label="Back to conversations" className="vt-btn vt-btn-quiet px-2.5 md:hidden">&larr;</button>
        <Avatar name={conv.other.name} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{conv.other.name}</p>
          <p className="truncate text-xs text-subtle">{ROLE_LABEL[conv.other.role] ?? conv.other.role}</p>
        </div>
        {status && (
          <span className="hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 text-xs text-muted sm:flex">
            <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[status]}`} />{STATUS_LABEL[status as ContentStatus] ?? status}
          </span>
        )}
        {conv.topic && (
          <Link href={pieceHref(side, conv.topic.id)} className="vt-btn vt-btn-quiet h-8 shrink-0 text-xs">
            Open piece <ExternalIcon size={13} />
          </Link>
        )}
      </header>

      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto"
        onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}>
        <div ref={content} className="mx-auto w-full max-w-3xl px-4 py-5 md:px-8">
          <h2 className="text-lg font-semibold leading-snug [overflow-wrap:anywhere]">{conv.topic?.title ?? `You and ${conv.other.name}`}</h2>
          <p className="mt-1 text-xs text-subtle">
            {conv.topic ? "The piece this conversation is about. Change it under the box." : "No piece linked yet: pick one under the box so you both, and Inki, know what you mean."}
          </p>
          {error && <p role="alert" className="mt-3 rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-2 text-sm text-[var(--vt-blocker)]">{error}</p>}
          {more && <div className="mt-4 text-center"><button type="button" onClick={loadOlder} className="vt-btn vt-btn-quiet text-xs">Show earlier messages</button></div>}
          {msgs === null && !error && <div className="mt-5 space-y-4">{[0, 1, 2].map((i) => <div key={i} className="h-14 animate-pulse rounded-xl bg-sunken" />)}</div>}
          {msgs?.length === 0 && (
            <p className="mt-8 text-center text-sm text-muted">Nothing here yet. Say hello to {conv.other.name.split(" ")[0]}.</p>
          )}
          <ol className="mt-4 flex flex-col gap-3">
            {msgs?.map((m, i) => (
              <Fragment key={m.id}>
                {(i === 0 || new Date(msgs[i - 1].created_at).toDateString() !== new Date(m.created_at).toDateString())
                  && <DayMark iso={m.created_at} />}
                <Row m={m} me={me} side={side} conversationId={conv.id} onJump={jump} onView={setViewing}
                  onReply={() => { setEditing(null); setReplyTo(m); }} onEdit={() => { setReplyTo(null); setEditing(m); }}
                  onDelete={() => remove(m)} />
              </Fragment>
            ))}
          </ol>
          {inki === "failed" && (
            <p className="flex items-center gap-2 py-3 text-[13px] text-muted" role="status">
              <InkiIcon size={22} /> {INKI} couldn&apos;t answer this time. Ask again in a moment.
            </p>
          )}
          {thinking && (
            <p className="flex items-center gap-2 py-3 text-[13px] text-muted" aria-live="polite">
              <InkiIcon size={22} /> {INKI} is reading the conversation
              <span className="vt-typing inline-flex gap-1"><span className="h-1.5 w-1.5 rounded-full bg-subtle" /><span className="h-1.5 w-1.5 rounded-full bg-subtle" /><span className="h-1.5 w-1.5 rounded-full bg-subtle" /></span>
            </p>
          )}
        </div>
      </div>

      <Composer conv={conv} me={me} side={side} initialPiece={initialPiece} replyTo={replyTo} editing={editing}
        quiet={Boolean(msgs?.length === 0)} onCancel={() => { setReplyTo(null); setEditing(null); }}
        onSent={(m) => { stick.current = true; merge([m]); setReplyTo(null); setEditing(null); }} />
      {viewing && <Viewer file={viewing} conversationId={conv.id} onClose={() => setViewing(null)} />}
    </>
  );
}

function Row({ m, me, side, conversationId, onJump, onView, onReply, onEdit, onDelete }: {
  m: ChatMessage; me: Me; side: "creator" | "manager"; conversationId: number; onJump: (id: number) => void;
  onView: (f: SharedFile) => void; onReply: () => void; onEdit: () => void; onDelete: () => void;
}) {
  const inki = m.kind === "inki";
  const mine = m.sender?.id === me.id;
  const owner = mine || (inki && m.asked_by?.id === me.id);
  const when = new Date(m.created_at);
  const name = inki ? INKI : mine ? "You" : m.sender?.name ?? "Someone";
  // Meeting links pasted into the words become a Join card under them; a call shared the older way keeps its own.
  const calls = m.deleted ? [] : [...(m.call ? [m.call] : []), ...meetingLinks(m.text).filter((c) => c.url !== m.call?.url)];
  const bubble = inki
    ? "rounded-2xl rounded-tl-md border border-accent/25 bg-accent/[0.07]"
    : mine ? "rounded-2xl rounded-br-md bg-accent text-accent-ink" : "rounded-2xl rounded-bl-md bg-sunken";
  return (
    // Yours on the right, theirs on the left, Inki on the left with its own mark: who said what at a glance.
    <li data-message={m.id} data-mine={mine || undefined} className={`group flex items-end gap-2 ${mine ? "flex-row-reverse" : ""}`}>
      {!mine && (inki ? <InkiIcon size={28} className="mb-5" /> : <span className="mb-5"><Avatar name={m.sender?.name ?? "?"} size={28} /></span>)}
      <div className={`flex min-w-0 max-w-[min(34rem,85%)] flex-col gap-1 ${mine ? "items-end" : "items-start"}`}>
        {!mine && (
          <span className="px-1 text-[11px] text-subtle">
            <span className="font-medium text-muted">{name}</span>
            {inki && m.asked_by && <> · answering {m.asked_by.id === me.id ? "you" : m.asked_by.name}</>}
          </span>
        )}
        <div className="relative flex max-w-full items-start gap-1">
          <div className={`min-w-0 px-3.5 py-2 ${m.deleted ? "rounded-2xl border border-dashed border-line" : bubble}`}>
            {m.reply_to && !m.deleted && (
              <button type="button" onClick={() => onJump(m.reply_to!.id)}
                className={`mb-1.5 flex w-full max-w-full items-start gap-1.5 rounded-lg border-l-2 px-2 py-1 text-left text-xs ${
                  mine ? "border-white/60 bg-white/15 text-accent-ink/90" : "border-accent/50 bg-raised/70 text-muted hover:text-ink"}`}>
                <span className="min-w-0"><span className="font-semibold">{m.reply_to.sender}</span>{" "}
                  <span className="[overflow-wrap:anywhere]">{m.reply_to.deleted ? "deleted message" : m.reply_to.excerpt}</span></span>
              </button>
            )}
            {m.deleted ? (
              <p className="text-sm text-subtle">This message was deleted.</p>
            ) : m.text ? (
              <p className="whitespace-pre-wrap text-sm leading-6 [overflow-wrap:anywhere]"><RichText text={m.text} mine={mine} /></p>
            ) : null}
          </div>
          {!m.deleted && (
            // Beside the bubble on hover with a mouse; on a touch screen there is no hover, so it stays shown.
            <div className={`absolute top-0 z-10 flex gap-0.5 rounded-lg border border-line bg-raised p-0.5 opacity-0 shadow-sm transition-opacity focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:static [@media(hover:none)]:opacity-100 [@media(hover:none)]:shadow-none ${
              mine ? "right-full mr-1.5 [@media(hover:none)]:order-first [@media(hover:none)]:mr-0" : "left-full ml-1.5 [@media(hover:none)]:ml-0"}`}>
              <IconButton label="Reply" onClick={onReply}><ReplyIcon size={14} /></IconButton>
              {mine && !inki && <IconButton label="Edit" onClick={onEdit}><PencilIcon size={14} /></IconButton>}
              {owner && <IconButton label="Delete for everyone" onClick={onDelete}><TrashIcon size={14} /></IconButton>}
            </div>
          )}
        </div>
        {calls.map((c) => <CallCard key={c.url} call={c} who={mine ? "You" : name} />)}
        {!m.deleted && m.files.length > 0 && <Files files={m.files} conversationId={conversationId} onView={onView} />}
        <span className={`flex flex-wrap items-center gap-x-2 gap-y-1 px-1 ${mine ? "justify-end" : ""}`}>
          {m.piece && !m.deleted && (
            <Link href={pieceHref(side, m.piece.id)} className="inline-flex max-w-full items-center rounded-full border border-line px-2 py-0.5 text-[11px] text-muted hover:text-accent">
              <span className="truncate">About: {m.piece.title}</span>
            </Link>
          )}
          <time dateTime={m.created_at} title={when.toLocaleString()} className="text-[11px] text-subtle">
            {when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </time>
          {m.edited && !m.deleted && <span className="text-[11px] text-subtle">edited</span>}
          {inki && <span className="text-[11px] text-subtle">AI-written. The brand team decides.</span>}
        </span>
      </div>
    </li>
  );
}

/** A quiet marker where the day changes, so a long conversation reads in order. */
function DayMark({ iso }: { iso: string }) {
  const d = new Date(iso);
  const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const diff = Math.round((day(new Date()) - day(d)) / 86_400_000);
  const label = diff === 0 ? "Today" : diff === 1 ? "Yesterday"
    : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: diff > 300 ? "numeric" : undefined });
  return (
    <li aria-hidden className="flex justify-center py-1">
      <span className="rounded-full bg-sunken px-2.5 py-0.5 text-[11px] text-subtle">{label}</span>
    </li>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
      className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-sunken hover:text-ink">{children}</button>
  );
}

// Meeting services whose links become a Join card, as the API's call links do (api/messages.py CALL_HOSTS).
const MEETING_HOSTS: Record<string, string> = {
  "meet.google.com": "Google Meet", "teams.microsoft.com": "Microsoft Teams", "teams.live.com": "Microsoft Teams",
  "zoom.us": "Zoom", "join.skype.com": "Skype", "meet.jit.si": "Jitsi Meet", "whereby.com": "Whereby",
};
const LINK = /https:\/\/[^\s<>"'\\]+/g;

function meetingProvider(url: string): string | null {
  try {
    const u = new URL(url);
    if (u.protocol !== "https:" || u.username || u.password || u.port) return null;
    const host = u.hostname.toLowerCase();
    const known = Object.keys(MEETING_HOSTS).find((h) => host === h || host.endsWith(`.${h}`));
    return known ? MEETING_HOSTS[known] : null;
  } catch {
    return null;
  }
}

function meetingLinks(text: string): { url: string; provider: string }[] {
  const out: { url: string; provider: string }[] = [];
  for (const raw of text.match(LINK) ?? []) {
    const url = raw.replace(/[).,;:!?]+$/, "");
    const provider = meetingProvider(url);
    if (provider && !out.some((c) => c.url === url)) out.push({ url, provider });
  }
  return out;
}

/** Words with @Inki marked and https links made clickable (opened in a new tab, telling the site nothing). */
function RichText({ text, mine }: { text: string; mine: boolean }) {
  const parts = text.split(/(https:\/\/[^\s<>"'\\]+|@inki\b)/i);
  return <>{parts.map((p, i) => {
    if (/^@inki$/i.test(p)) {
      return <span key={i} className={`rounded px-0.5 font-semibold ${mine ? "bg-white/20" : "bg-accent/12 text-accent"}`}>{p}</span>;
    }
    if (/^https:\/\//i.test(p)) {
      const url = p.replace(/[).,;:!?]+$/, "");
      const tail = p.slice(url.length);
      return <span key={i}><a href={url} target="_blank" rel="noopener noreferrer nofollow"
        className="break-all underline underline-offset-2 hover:no-underline">{url}</a>{tail}</span>;
    }
    return p;
  })}</>;
}

function CallCard({ call, who }: { call: { url: string; provider: string }; who: string }) {
  return (
    <div className="flex w-80 max-w-full items-center gap-3 rounded-xl border border-line bg-raised px-3.5 py-3">
      <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent/12 text-accent"><VideoIcon size={16} /></span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{call.provider} call</span>
        <span className="block text-[11px] text-subtle">{who} shared a meeting link</span>
      </span>
      <a href={call.url} target="_blank" rel="noopener noreferrer" className="vt-btn vt-btn-primary h-8 shrink-0 text-xs">Join</a>
    </div>
  );
}

// Files show as themselves: a picture, a playable video, a document's first page. Pictures and videos are
// viewed in place with no save option offered; that discourages, but can't prevent, a copy being kept.
function Files({ files, conversationId, onView }: { files: SharedFile[]; conversationId: number; onView: (f: SharedFile) => void }) {
  return (
    <div className="mt-2 flex flex-wrap items-start gap-2">
      {files.map((f) => f.kind === "image" ? (
        <button key={f.id} type="button" onClick={() => onView(f)} aria-label={`View ${f.name}`}
          className="overflow-hidden rounded-xl border border-line bg-sunken" onContextMenu={(e) => e.preventDefault()}>
          {/* eslint-disable-next-line @next/next/no-img-element -- served by our API, sized by the browser */}
          <img src={fileUrl(conversationId, f.id)} alt={f.name} draggable={false} loading="lazy"
            className="block max-h-56 max-w-[16rem] object-contain" />
        </button>
      ) : f.kind === "video" ? (
        <div key={f.id} className="w-80 max-w-full overflow-hidden rounded-xl border border-line bg-black" onContextMenu={(e) => e.preventDefault()}>
          <video src={fileUrl(conversationId, f.id)} poster={posterUrl(conversationId, f.id)} controls preload="metadata"
            controlsList="nodownload noplaybackrate noremoteplayback" disablePictureInPicture disableRemotePlayback className="block max-h-60 w-full" />
          <p className="flex justify-between gap-2 bg-raised px-3 py-1.5 text-[11px] text-muted">
            <span className="truncate">{f.name}</span>
            {f.duration ? <span className="shrink-0">{Math.floor(Math.round(f.duration) / 60)}:{String(Math.round(f.duration) % 60).padStart(2, "0")}</span> : null}
          </p>
        </div>
      ) : (
        <a key={f.id} href={fileUrl(conversationId, f.id)} target="_blank" rel="noopener noreferrer"
          className="flex w-64 max-w-full items-center gap-3 rounded-xl border border-line bg-raised p-2.5 hover:border-accent/40">
          {f.media_type === "application/pdf" ? <PdfThumb src={posterUrl(conversationId, f.id)} /> : (
            <span aria-hidden className="grid h-14 w-11 shrink-0 place-items-center rounded-md bg-sunken text-muted"><FileIcon size={18} /></span>
          )}
          <span className="min-w-0">
            <span className="block truncate text-sm font-medium">{f.name}</span>
            <span className="block text-[11px] text-subtle">{docKind(f.media_type)} · {size(f.bytes)}</span>
          </span>
        </a>
      ))}
    </div>
  );
}

function PdfThumb({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span aria-hidden className="grid h-14 w-11 shrink-0 place-items-center rounded-md bg-sunken text-muted"><FileIcon size={18} /></span>;
  // eslint-disable-next-line @next/next/no-img-element -- a small preview rendered by our API
  return <img src={src} alt="" onError={() => setFailed(true)} className="h-14 w-11 shrink-0 rounded-md border border-line bg-white object-cover object-top" />;
}

function docKind(type: string) {
  if (type === "application/pdf") return "PDF";
  if (type.includes("wordprocessingml")) return "Word";
  if (type.includes("presentationml")) return "PowerPoint";
  if (type.includes("spreadsheetml")) return "Excel";
  return "File";
}

function Viewer({ file, conversationId, onClose }: { file: SharedFile; conversationId: number; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  useModalFocus(panel, onClose);
  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4" onContextMenu={(e) => e.preventDefault()}>
      <div aria-hidden onClick={onClose} className="vt-backdrop absolute inset-0 bg-black/70 backdrop-blur-[2px]" />
      <div ref={panel} role="dialog" aria-modal="true" aria-label={file.name} className="relative flex max-h-full max-w-full flex-col items-center gap-2">
        <button type="button" onClick={onClose} aria-label="Close" className="self-end rounded-lg bg-black/50 p-1.5 text-white hover:bg-black/70"><CloseIcon size={18} /></button>
        {/* eslint-disable-next-line @next/next/no-img-element -- full size view of a shared picture */}
        <img src={fileUrl(conversationId, file.id)} alt={file.name} draggable={false}
          className="max-h-[calc(100dvh-6rem)] max-w-[calc(100vw-2rem)] select-none rounded-lg object-contain" />
        <p className="text-xs text-white/80">{file.name}</p>
      </div>
    </div>,
    document.body,
  );
}

function Composer({ conv, me, side, initialPiece, replyTo, editing, quiet, onCancel, onSent }: {
  conv: ConversationRow; me: Me; side: "creator" | "manager"; initialPiece: number | null; replyTo: ChatMessage | null;
  editing: ChatMessage | null; quiet: boolean; onCancel: () => void; onSent: (m: ChatMessage) => void;
}) {
  const [text, setText] = useState("");
  const [piece, setPiece] = useState<number | null>(initialPiece ?? conv.topic?.id ?? null);
  const [pieces, setPieces] = useState<ContentRow[] | null>(null);
  const [files, setFiles] = useState<Pending[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState<null | { resend: () => Promise<void> }>(null);
  const [inkiOn, setInkiOn] = useState<boolean | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  // One id per message being sent: a retry of the same message reuses it, so it is stored once. It belongs
  // to that exact message: change the words, files or reply and it is a new message with a new id.
  const pending = useRef<{ id: string; of: string } | null>(null);
  // What was being written when an edit started, given back when the edit ends.
  const [draft, setDraft] = useState("");

  useEffect(() => {
    const creatorId = side === "creator" ? null : conv.other.id;
    listContents(side === "creator")
      .then((rows) => setPieces(rows.filter((r) => creatorId === null || r.created_by === creatorId)))
      .catch(() => setPieces([]));
  }, [conv.other.id, side]);
  useEffect(() => { inkiConsent().then((c) => setInkiOn(Boolean(c.accepted_at))).catch(() => setInkiOn(null)); }, []);

  // Editing loads the words into the box; leaving edit mode empties it again.
  const [editingId, setEditingId] = useState<number | null>(null);
  if ((editing?.id ?? null) !== editingId) {
    if (editingId === null) setDraft(text);  // starting an edit: keep the draft aside
    setEditingId(editing?.id ?? null);
    setText(editing ? editing.text : draft);
  }
  useEffect(() => { if (editing || replyTo) box.current?.focus(); }, [editing, replyTo]);

  const mention = useMemo(() => {
    const m = /(^|\s)@(\w*)$/.exec(text);
    return Boolean(m && INKI.toLowerCase().startsWith(m[2].toLowerCase()) && m[2].toLowerCase() !== INKI.toLowerCase());
  }, [text]);

  const takeMention = () => {
    setText((t) => t.replace(/@(\w*)$/, `@${INKI} `));
    box.current?.focus();
  };

  const attach = (list: FileList | null) => {
    if (!list) return;
    const room = MAX_FILES - files.length;
    if (list.length > room) setError(`Up to ${MAX_FILES} files per message.`);
    [...list].slice(0, Math.max(0, room)).forEach((f) => {
      const key = `${f.name}-${f.size}-${Math.random()}`;
      setFiles((all) => [...all, { key, name: f.name, state: "uploading" }]);
      upload(f).then((u) => setFiles((all) => all.map((p) => p.key === key ? { ...p, state: "ready", file: {
        id: u.id, kind: u.media_type.startsWith("image/") ? "image" : u.media_type.startsWith("video/") ? "video" : "document",
        name: u.name ?? f.name, media_type: u.media_type, bytes: u.bytes } } : p)))
        .catch((e: Error) => setFiles((all) => all.map((p) => p.key === key ? { ...p, state: "failed", error: e.message } : p)));
    });
  };

  const send = async (body: { text?: string; call_url?: string }, plain = false): Promise<boolean> => {
    if (sending) return false;
    // A call link, or a ready question for Inki, goes on its own: no staged files, not as a reply.
    const alone = plain || Boolean(body.call_url);
    const ids = alone ? [] : files.filter((f) => f.state === "ready").map((f) => f.file!.id);
    const message = { ...body, content_id: piece, files: ids, reply_to: alone ? null : replyTo?.id ?? null };
    const of = JSON.stringify(message);
    if (pending.current?.of !== of) pending.current = { id: newClientId(), of };
    setSending(true);
    setError(null);
    const attempt = () => sendMessage(conv.id, { ...message, client_id: pending.current!.id });
    try {
      const m = await attempt();
      pending.current = null;
      if (!alone) setFiles([]);
      onSent(m);
      return true;
    } catch (e) {
      if (needsInkiConsent(e)) {
        // Asked once, before the first @Inki: agreeing sends the same message; declining sends nothing.
        setConsent({ resend: async () => {
          await acceptInki();  // a failure is shown in the dialog, which stays open
          setInkiOn(true);
          setConsent(null);
          if (await send(body, plain) && !plain) setText("");
        } });
        return false;
      }
      if (e instanceof ApiError && e.status < 500) pending.current = null;
      setError(e instanceof ApiError ? e.message : "Couldn't send. Check your connection and try again.");
      return false;
    } finally {
      setSending(false);
    }
  };

  const submit = async () => {
    const t = text.trim();
    if (editing) {
      if (!t || t === editing.text) { onCancel(); return; }
      setSending(true);
      try { onSent(await editMessage(conv.id, editing.id, t)); }
      catch (e) { setError((e as Error).message); }
      finally { setSending(false); }
      return;
    }
    const ready = files.some((f) => f.state === "ready");
    if (!t && !ready) return;
    if (files.some((f) => f.state === "uploading")) { setError("Wait for the files to finish uploading."); return; }
    if (files.some((f) => f.state === "failed")) { setError("Some files didn't upload. Remove them, or attach them again."); return; }
    if (await send({ text: t })) { setText(""); setDraft(""); }
  };


  const ask = (q: string) => send({ text: `@${INKI} ${q}` }, true);
  const first = conv.other.name.split(" ")[0];
  const canSend = editing ? text.trim().length > 0 : (text.trim().length > 0 || files.some((f) => f.state === "ready"));

  return (
    <div className="border-t border-line bg-surface/40 px-3 py-3 md:px-6">
      <div className="mx-auto w-full max-w-3xl">
        {!editing && !replyTo && !text && !quiet && (
          <div className="mb-2 hidden flex-wrap items-center gap-1.5 rounded-xl border border-line bg-raised px-3 py-2 md:flex">
            <InkiIcon size={18} /><span className="mr-1 text-xs text-muted">Ask {INKI}</span>
            {ASK_INKI.map((q) => (
              <button key={q} type="button" onClick={() => ask(q)} disabled={sending}
                className="rounded-full border border-line px-2.5 py-0.5 text-xs text-muted transition hover:border-accent/40 hover:text-ink">{q}</button>
            ))}
          </div>
        )}
        {error && <p role="alert" className="mb-2 rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-1.5 text-[13px] text-[var(--vt-blocker)]">{error}</p>}
        <div className="vt-composer rounded-xl border border-line bg-raised">
          {(replyTo || editing) && (
            <div className="flex items-center gap-2 border-b border-line px-3 py-1.5 text-xs text-muted">
              {editing ? <PencilIcon size={12} /> : <ReplyIcon size={12} />}
              <span className="min-w-0 flex-1 truncate">
                {editing ? "Editing your message" : <>Replying to <span className="font-medium text-ink">{replyTo!.kind === "inki" ? INKI : replyTo!.sender?.id === me.id ? "yourself" : replyTo!.sender?.name}</span>: {replyTo!.text || "a file"}</>}
              </span>
              <button type="button" onClick={onCancel} className="rounded px-1.5 py-0.5 hover:bg-sunken hover:text-ink">Cancel <kbd className="text-[10px] text-subtle">Esc</kbd></button>
            </div>
          )}
          {mention && (
            <button type="button" onClick={takeMention} className="flex w-full items-center gap-2 border-b border-line px-3 py-1.5 text-left text-[13px] hover:bg-sunken">
              <InkiIcon size={18} /><span><span className="font-medium">@{INKI}</span> <span className="text-muted">asks the assistant about this conversation</span></span>
              <kbd className="ml-auto rounded border border-line px-1 text-[10px] text-subtle">Tab</kbd>
            </button>
          )}
          {files.length > 0 && (
            <ul className="flex flex-wrap gap-1.5 border-b border-line px-3 py-2">
              {files.map((f) => (
                <li key={f.key} className={`flex max-w-[20rem] items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
                  f.state === "failed" ? "border-[var(--vt-blocker)] text-[var(--vt-blocker)]" : "border-line text-muted"}`} title={f.error}>
                  <span className="truncate">{f.name}</span>
                  <span className="shrink-0 truncate text-subtle">{f.state === "uploading" ? "uploading" : f.state === "failed" ? `failed: ${f.error ?? "try again"}` : ""}</span>
                  <button type="button" aria-label={`Remove ${f.name}`} onClick={() => setFiles((all) => all.filter((p) => p.key !== f.key))}
                    className="shrink-0 hover:text-ink"><CloseIcon size={11} /></button>
                </li>
              ))}
            </ul>
          )}
          <label className="sr-only" htmlFor={`msg-${conv.id}`}>Message</label>
          <textarea id={`msg-${conv.id}`} ref={box} value={text} rows={2} maxLength={4000}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && (editing || replyTo)) { e.preventDefault(); onCancel(); return; }
              if (mention && (e.key === "Tab" || e.key === "Enter")) { e.preventDefault(); takeMention(); return; }
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); }
            }}
            placeholder={editing ? "Edit your message" : `Message ${first}. Mention @${INKI} to ask the assistant, or paste a Meet, Teams or Zoom link to talk.`}
            className="block max-h-48 min-h-[3.5rem] w-full resize-none bg-transparent px-3 py-2.5 text-sm outline-none [field-sizing:content]" />
          <div className="flex flex-wrap items-center gap-1.5 px-2 pb-2">
            <span className="hidden items-center gap-1.5 px-1 text-[11px] text-subtle sm:flex">As {me.name}</span>
            {!editing && (
              <>
                <input ref={picker} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { attach(e.target.files); e.target.value = ""; }} />
                <button type="button" onClick={() => picker.current?.click()} disabled={files.length >= MAX_FILES}
                  className="vt-btn vt-btn-quiet h-8 px-2 text-xs" title="Images, documents, videos up to 10 minutes"><PaperclipIcon size={14} /> Files</button>
                <label className="flex min-w-0 items-center gap-1 text-[11px] text-muted">
                  <span className="sr-only sm:not-sr-only">About</span>
                  <select value={piece ?? ""} onChange={(e) => setPiece(e.target.value ? Number(e.target.value) : null)}
                    className="vt-input h-8 min-w-0 max-w-[12rem] truncate py-0 text-xs">
                    <option value="">No piece</option>
                    {pieces?.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
                    {piece && pieces && !pieces.some((p) => p.id === piece) && <option value={piece}>{conv.topic?.id === piece ? conv.topic.title : `Piece #${piece}`}</option>}
                  </select>
                </label>
              </>
            )}
            <button type="button" onClick={() => void submit()} disabled={!canSend || sending}
              className="vt-btn vt-btn-primary ml-auto h-8 px-3 text-xs">{editing ? "Save" : <><ArrowUpIcon size={13} /> Send</>}</button>
          </div>
        </div>
        {/* The privacy note hides on a phone; the way to turn Inki off never does, since the consent says it is here. */}
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
          <span className="hidden items-center gap-1 sm:flex"><ShieldIcon size={11} /> Encrypted at rest. Deleting removes a message and its files for everyone.</span>
          {inkiOn && (
            <button type="button" className="underline-offset-2 hover:text-ink hover:underline"
              onClick={() => withdrawInki().then(() => setInkiOn(false))
                .catch((e: Error) => setError(`${INKI} is still on: ${e.message}. Try again.`))}>
              {INKI} may read conversations you ask it into · Turn off
            </button>
          )}
        </p>
      </div>
      {consent && <InkiConsent onAccept={consent.resend} onDecline={() => setConsent(null)} />}
    </div>
  );
}

function InkiConsent({ onAccept, onDecline }: { onAccept: () => Promise<void>; onDecline: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  useModalFocus(panel, onDecline);
  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4">
      <div aria-hidden onClick={onDecline} className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]" />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="vt-pop relative w-full max-w-md rounded-2xl border border-line bg-raised p-5 shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-center gap-3"><InkiIcon size={36} /><h2 id={titleId} className="text-base font-semibold">Let {INKI} read this conversation?</h2></div>
        <ul className="mt-4 space-y-2 text-sm leading-6 text-muted">
          <li><span className="font-medium text-ink">What it reads:</span> the last few messages from both of you, the pieces linked here that you can both open, and up to three files shared here.</li>
          <li><span className="font-medium text-ink">What it never sees:</span> your other conversations, other people&apos;s pieces, or anything else in the workspace.</li>
          <li><span className="font-medium text-ink">Where it goes:</span> a hosted AI model, with confidential terms hidden first. The other person sees that you asked {INKI}.</li>
          <li>You can turn this off any time, under the message box.</li>
        </ul>
        {failed && <p role="alert" className="mt-4 rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-2 text-[13px] text-[var(--vt-blocker)]">{failed}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onDecline} className="vt-btn vt-btn-quiet">Not now</button>
          <button type="button" disabled={busy} className="vt-btn vt-btn-primary" onClick={async () => {
            setBusy(true);
            setFailed(null);
            try { await onAccept(); }
            catch (e) { setFailed(`That didn't save (${(e as Error).message}). Try again.`); }
            finally { setBusy(false); }
          }}>Allow and send</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

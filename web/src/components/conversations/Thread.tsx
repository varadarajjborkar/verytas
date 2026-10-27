"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ACCEPT, CALL_STARTERS, type ChatMessage, CONVERSATIONS_SEEN_EVENT, type ConversationRow, MAX_FILES,
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

export function Thread({ conv, me, side, subscribe, thinking, initialPiece, onBack, onRead }: {
  conv: ConversationRow; me: Me; side: "creator" | "manager"; subscribe: (l: Listener) => () => void;
  thinking: boolean; initialPiece: number | null; onBack: () => void; onRead: () => void;
}) {
  const [msgs, setMsgs] = useState<ChatMessage[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [editing, setEditing] = useState<ChatMessage | null>(null);
  const [viewing, setViewing] = useState<SharedFile | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const marked = useRef(0);
  const lastRef = useRef(0);

  const merge = useCallback((incoming: ChatMessage[]) => setMsgs((list) => {
    const byId = new Map((list ?? []).map((m) => [m.id, m]));
    incoming.forEach((m) => byId.set(m.id, m));
    return [...byId.values()].sort((a, b) => a.id - b.id);
  }), []);

  useEffect(() => {
    listMessages(conv.id).then((m) => { setMsgs(m); setMore(m.length >= PAGE); }).catch((e: Error) => setError(e.message));
  }, [conv.id]);

  const lastId = msgs?.at(-1)?.id ?? 0;
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
      markRead(conv.id, lastId).then(() => { onRead(); window.dispatchEvent(new Event(CONVERSATIONS_SEEN_EVENT)); }).catch(() => {});
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

  const remove = async (m: ChatMessage) => {
    if (!window.confirm("Delete this message for everyone? Its files go too.")) return;
    try { merge([await deleteMessage(conv.id, m.id)]); } catch (e) { setError((e as Error).message); }
  };

  const jump = (id: number) => {
    const el = scroller.current?.querySelector<HTMLElement>(`[data-message="${id}"]`);
    if (!el) return;
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
        <div className="mx-auto w-full max-w-3xl px-4 py-5 md:px-8">
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
          <ol className="mt-3 divide-y divide-line">
            {msgs?.map((m) => (
              <Row key={m.id} m={m} me={me} side={side} conversationId={conv.id} onJump={jump} onView={setViewing}
                onReply={() => { setEditing(null); setReplyTo(m); }} onEdit={() => { setReplyTo(null); setEditing(m); }}
                onDelete={() => remove(m)} />
            ))}
          </ol>
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
  return (
    <li data-message={m.id} className={`group relative flex gap-3 py-4 transition-colors ${inki ? "-mx-3 rounded-xl bg-accent/[0.05] px-3" : ""}`}>
      {inki ? <InkiIcon size={32} /> : <Avatar name={m.sender?.name ?? "?"} size={32} />}
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-sm font-semibold">{name}</span>
          {inki && m.asked_by && <span className="text-xs text-subtle">answering {m.asked_by.id === me.id ? "you" : m.asked_by.name}</span>}
          <time dateTime={m.created_at} title={when.toLocaleString()} className="ml-auto text-[11px] text-subtle">
            {when.toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
          </time>
        </p>
        {m.reply_to && (
          <button type="button" onClick={() => onJump(m.reply_to!.id)}
            className="mt-1 flex max-w-full items-start gap-2 rounded-md border-l-2 border-accent/40 bg-sunken px-2.5 py-1 text-left text-xs text-muted hover:text-ink">
            <ReplyIcon size={12} className="mt-0.5 shrink-0 -scale-x-100" />
            <span className="min-w-0"><span className="font-medium">{m.reply_to.sender}</span>{" "}
              <span className="[overflow-wrap:anywhere]">{m.reply_to.deleted ? <em>deleted message</em> : m.reply_to.excerpt}</span></span>
          </button>
        )}
        {m.deleted ? (
          <p className="mt-1 text-sm italic text-subtle">This message was deleted.</p>
        ) : (
          <>
            {m.text && <p className="mt-1 whitespace-pre-wrap text-sm leading-6 [overflow-wrap:anywhere]"><Mentions text={m.text} /></p>}
            {m.call && <CallCard call={m.call} who={mine ? "You" : name} />}
            {m.files.length > 0 && <Files files={m.files} conversationId={conversationId} onView={onView} />}
            <p className="mt-1.5 flex flex-wrap items-center gap-2">
              {m.piece && (
                <Link href={pieceHref(side, m.piece.id)} className="inline-flex max-w-full items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] text-muted hover:text-accent">
                  <span className="truncate">About: {m.piece.title}</span>
                </Link>
              )}
              {m.edited && <span className="text-[11px] text-subtle">edited</span>}
              {inki && <span className="text-[11px] text-subtle">AI-written. The brand team decides.</span>}
            </p>
          </>
        )}
      </div>
      {!m.deleted && (
        <div className="absolute -top-3.5 right-1 z-10 flex gap-0.5 rounded-lg border border-line bg-raised p-0.5 opacity-0 shadow-sm transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <IconButton label="Reply" onClick={onReply}><ReplyIcon size={14} /></IconButton>
          {mine && !inki && <IconButton label="Edit" onClick={onEdit}><PencilIcon size={14} /></IconButton>}
          {owner && <IconButton label="Delete for everyone" onClick={onDelete}><TrashIcon size={14} /></IconButton>}
        </div>
      )}
    </li>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
      className="grid h-7 w-7 place-items-center rounded-md text-muted hover:bg-sunken hover:text-ink">{children}</button>
  );
}

function Mentions({ text }: { text: string }) {
  const parts = text.split(/(@inki\b)/i);
  return <>{parts.map((p, i) => /^@inki$/i.test(p)
    ? <span key={i} className="rounded bg-accent/12 px-0.5 font-semibold text-accent">{p}</span> : p)}</>;
}

function CallCard({ call, who }: { call: { url: string; provider: string }; who: string }) {
  return (
    <div className="mt-2 flex w-80 max-w-full items-center gap-3 rounded-xl border border-line bg-raised px-3.5 py-3">
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
            controlsList="nodownload noplaybackrate" disablePictureInPicture className="block max-h-60 w-full" />
          <p className="flex justify-between gap-2 bg-raised px-3 py-1.5 text-[11px] text-muted">
            <span className="truncate">{f.name}</span>
            {f.duration ? <span className="shrink-0">{Math.floor(f.duration / 60)}:{String(Math.round(f.duration % 60)).padStart(2, "0")}</span> : null}
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
  const [calling, setCalling] = useState(false);
  const [link, setLink] = useState("");
  const [consent, setConsent] = useState<null | { resend: () => Promise<void> }>(null);
  const [inkiOn, setInkiOn] = useState<boolean | null>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  // One id per message being sent: a retry of the same message reuses it, so it is stored once.
  const pending = useRef<string | null>(null);

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
    setEditingId(editing?.id ?? null);
    setText(editing ? editing.text : "");
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

  const send = async (body: { text?: string; call_url?: string }): Promise<boolean> => {
    if (sending) return false;
    setSending(true);
    setError(null);
    pending.current ??= newClientId();
    const ids = files.filter((f) => f.state === "ready").map((f) => f.file!.id);
    const attempt = () => sendMessage(conv.id, { ...body, content_id: piece, client_id: pending.current!,
      files: body.call_url ? [] : ids, reply_to: replyTo?.id ?? null });
    try {
      const m = await attempt();
      pending.current = null;
      if (!body.call_url) setFiles([]);
      onSent(m);
      return true;
    } catch (e) {
      if (needsInkiConsent(e)) {
        // Asked once, before the first @Inki: agreeing sends the same message; declining sends nothing.
        setConsent({ resend: async () => {
          await acceptInki();
          setInkiOn(true);
          setConsent(null);
          if (await send(body)) setText("");
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
      try { onSent(await editMessage(conv.id, editing.id, t)); setText(""); }
      catch (e) { setError((e as Error).message); }
      finally { setSending(false); }
      return;
    }
    const ready = files.some((f) => f.state === "ready");
    if (!t && !ready) return;
    if (files.some((f) => f.state === "uploading")) { setError("Wait for the files to finish uploading."); return; }
    if (await send({ text: t })) setText("");
  };

  const shareCall = async () => {
    const url = link.trim();
    if (url && await send({ call_url: url })) { setLink(""); setCalling(false); }
  };

  const ask = async (q: string) => { if (await send({ text: `@${INKI} ${q}` })) setText(""); };
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
        {calling && (
          <div className="mb-2 rounded-xl border border-line bg-raised p-3">
            <div className="flex items-start justify-between gap-2">
              <p className="text-[13px] font-medium">Share a call link</p>
              <button type="button" onClick={() => setCalling(false)} aria-label="Close" className="grid h-6 w-6 place-items-center rounded text-muted hover:text-ink"><CloseIcon size={13} /></button>
            </div>
            <p className="mt-0.5 text-xs text-muted">Start a meeting where your company already meets, copy its link and paste it here.</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {CALL_STARTERS.map((s) => <a key={s.name} href={s.start} target="_blank" rel="noopener noreferrer" className="vt-btn vt-btn-quiet h-8 text-xs">New {s.name}</a>)}
            </div>
            <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); void shareCall(); }}>
              <label className="sr-only" htmlFor={`call-${conv.id}`}>Meeting link</label>
              <input id={`call-${conv.id}`} value={link} onChange={(e) => setLink(e.target.value)} inputMode="url"
                placeholder="https://meet.google.com/abc-defg-hij" className="vt-input min-w-0 flex-1 text-sm" />
              <button type="submit" disabled={!link.trim() || sending} className="vt-btn vt-btn-primary text-sm">Share</button>
            </form>
          </div>
        )}
        <div className="rounded-xl border border-line bg-raised focus-within:border-accent/50">
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
                <li key={f.key} className={`flex max-w-[14rem] items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs ${
                  f.state === "failed" ? "border-[var(--vt-blocker)] text-[var(--vt-blocker)]" : "border-line text-muted"}`} title={f.error}>
                  <span className="truncate">{f.name}</span>
                  <span className="shrink-0 text-subtle">{f.state === "uploading" ? "uploading" : f.state === "failed" ? "failed" : ""}</span>
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
            placeholder={editing ? "Edit your message" : `Reply to ${first}...  Mention @${INKI} to ask the assistant`}
            className="block max-h-48 min-h-[3.5rem] w-full resize-none bg-transparent px-3 py-2.5 text-sm outline-none [field-sizing:content]" />
          <div className="flex flex-wrap items-center gap-1.5 px-2 pb-2">
            <span className="hidden items-center gap-1.5 px-1 text-[11px] text-subtle sm:flex">As {me.name}</span>
            {!editing && (
              <>
                <input ref={picker} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => { attach(e.target.files); e.target.value = ""; }} />
                <button type="button" onClick={() => picker.current?.click()} disabled={files.length >= MAX_FILES}
                  className="vt-btn vt-btn-quiet h-8 px-2 text-xs" title="Images, documents, videos up to 10 minutes"><PaperclipIcon size={14} /> Files</button>
                <button type="button" onClick={() => setCalling((c) => !c)} aria-expanded={calling} className="vt-btn vt-btn-quiet h-8 px-2 text-xs">
                  <VideoIcon size={14} /> Call
                </button>
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
        <p className="mt-1.5 hidden flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle sm:flex">
          <span className="flex items-center gap-1"><ShieldIcon size={11} /> Encrypted at rest. Deleting removes a message and its files for everyone.</span>
          {inkiOn && (
            <button type="button" className="underline-offset-2 hover:text-ink hover:underline"
              onClick={() => withdrawInki().then(() => setInkiOn(false)).catch(() => {})}>
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
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onDecline} className="vt-btn vt-btn-quiet">Not now</button>
          <button type="button" disabled={busy} onClick={async () => { setBusy(true); try { await onAccept(); } finally { setBusy(false); } }}
            className="vt-btn vt-btn-primary">Allow and send</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

"use client";

import { type ActionEvent, type ParseResult, Renderer } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { type ChatStore, imageToDataUrl, openChatStore, type StoredMessage, type ThreadSummary } from "@/lib/chat-store";
import { usePersistedFlag } from "@/lib/persisted-flag";
import { readStream } from "@/lib/sse";
import { Drawer } from "./Drawer";
import { Logo } from "./Logo";
import { ArrowRightIcon, ArrowUpIcon, ChatIcon, CloseIcon, HistoryIcon, PanelIcon, PaperclipIcon, PlusIcon, SparkIcon, TrashIcon } from "./Icons";
import { useToast } from "./Toaster";
import { useViewer } from "./Viewer";
import { AiInfoButton } from "./AiInfo";

// Ask Verytas, full page. The model answers in OpenUI Lang (charts, tables,
// callouts) streamed from /api/chat and drawn by OpenUI's renderer in the app's
// own theme. Conversations are kept per person (lib/chat-store) and listed in a
// rail, like any chat app. Images can be attached and are stored with the
// conversation; the current model can't see them and is told so.

type Message = StoredMessage & { id: number; error?: boolean; note?: string };
// One open conversation. Saves are chained on it, so a second save waits for the
// first one's id instead of creating a duplicate, and a save that finishes after
// the person moved on still lands on the conversation it belongs to.
type Conversation = { id: number | null; saving: Promise<void> };
const fresh = (id: number | null = null): Conversation => ({ id, saving: Promise.resolve() });

const MAX_IMAGES = 4;
// Each side starts from the questions its own work raises: a creator about their pieces and the rules,
// the brand team about the queue, the rules and the people.
const STARTERS = {
  creator: [
    { label: "How are my recent posts doing?", prompt: "How are my most recent pieces doing in review? What is still blocking them?" },
    { label: "What do I get flagged for most?", prompt: "Which issues come up most often in my pieces, and how do I avoid them?" },
    { label: "Which claims can I make?", prompt: "Which approved facts can I quote in a post right now, with their sources?" },
    { label: "Which words should I avoid?", prompt: "List the banned and preferred terms I should know, and any confidential names." },
  ],
  manager: [
    { label: "What needs a decision today?", prompt: "What is waiting for a decision, most urgent first, and why?" },
    { label: "Which rules get overridden most?", prompt: "Which rules do reviewers override most, and why might that be?" },
    { label: "How did blockers trend this month?", prompt: "Show how blockers trended over the last 30 days." },
    { label: "Who is drifting from the brand?", prompt: "Which creators' recent pieces drift furthest from the brand, and in what way?" },
  ],
};

/** Only web links from a model answer are opened; anything else (javascript:, data:) is ignored. */
function safeUrl(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}


const titleOf = (text: string) => (text.trim().replace(/\s+/g, " ").slice(0, 60) || "Image question");

function when(iso: string): string {
  const d = new Date(iso);
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (days < 1) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (days < 7) return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

export function AskVerytas() {
  const { side } = useViewer();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState("");
  const [store, setStore] = useState<ChatStore | null>(null);
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<number | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  const [railHidden, setRailHidden] = usePersistedFlag("vt-ask-rail-collapsed", false);
  const conversation = useRef<Conversation>(fresh());
  const opening = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const end = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const toast = useToast();

  useEffect(() => {
    openChatStore().then(async (s) => {
      setStore(s);
      setThreads(await s.list().catch(() => []));
    });
  }, []);
  // Follow the answer only while the reader is at the bottom; scrolling up to
  // read something earlier is never fought.
  useEffect(() => {
    const el = scroller.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120) end.current?.scrollIntoView({ block: "end" });
  }, [messages]);
  useEffect(() => () => abort.current?.abort(), []);

  function persist(all: Message[], conv: Conversation) {
    if (!store) return;
    const kept = all.filter((m) => !m.error && (m.content || m.images?.length))
      .map(({ role, content, images: imgs }) => (imgs?.length ? { role, content, images: imgs } : { role, content }));
    if (!kept.length) return;
    conv.saving = conv.saving.then(async () => {
      try {
        const saved = await store.save(conv.id, titleOf(kept.find((m) => m.role === "user")?.content ?? ""), kept);
        conv.id = saved.id;
        if (conversation.current === conv) setThreadId(saved.id);
        setThreads((ts) => [saved, ...ts.filter((t) => t.id !== saved.id)]);
      } catch (err) {
        toast({ kind: "warning", title: "Couldn't save this chat", detail: (err as Error).message });
      }
    });
  }

  const send = useCallback(async (text: string, attach: string[] = []) => {
    const question = text.trim();
    if ((!question && !attach.length) || streaming) return;
    const history: Message[] = [...messages.filter((m) => !m.error),
      { id: nextId.current++, role: "user", content: question, ...(attach.length ? { images: attach } : {}) }];
    const answerId = nextId.current++;
    let answer: Message = { id: answerId, role: "assistant", content: "" };
    setMessages([...history, answer]);
    setInput("");
    setImages([]);
    if (box.current) box.current.style.height = "auto";
    setStreaming(true);
    setStatus("Verytas is answering");
    const write = (fn: (m: Message) => Message) => {
      answer = fn(answer);
      setMessages((all) => all.map((m) => (m.id === answerId ? answer : m)));
    };
    const controller = new AbortController();
    abort.current = controller;
    const conv = conversation.current;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Images stay in the browser and the stored thread; the model only hears that they exist.
        body: JSON.stringify({ messages: history.map(({ role, content, images: imgs }) =>
          ({ role, content: content || "(see attached images)", imageCount: imgs?.length ?? 0 })) }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.error ?? "Ask Verytas is unavailable right now.");
      }
      await readStream(res, (t) => write((m) => ({ ...m, content: m.content + t })));
      write((m) => (m.content ? m : { ...m, note: "No answer came back. Try asking another way." }));
      setStatus("Answer ready");
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        write((m) => (m.content ? m : { ...m, note: "Stopped." }));
        setStatus("Stopped");
      } else {
        write((m) => ({ ...m, error: true, content: (err as Error).message }));
        setStatus("The answer failed");
      }
    } finally {
      if (abort.current === controller) {
        setStreaming(false);
        abort.current = null;
      }
      // Saved even when the person left mid-answer: it goes to the conversation it was asked in.
      persist([...history, answer], conv);
    }
  // persist reads the store through this render's closure, which is what send needs.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, streaming, store]);

  const onAction = useCallback((event: ActionEvent) => {
    if (event.type === "continue_conversation") void send(event.humanFriendlyMessage);
    else if (event.type === "open_url") {
      const url = safeUrl(event.params?.url);
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    }
  }, [send]);

  function stopAndClear() {
    abort.current?.abort();
    abort.current = null;
    setStreaming(false);
    setInput("");
    setImages([]);
  }

  function newChat() {
    stopAndClear();
    opening.current++;
    conversation.current = fresh();
    setMessages([]);
    setThreadId(null);
    setRailOpen(false);
    box.current?.focus();
  }

  async function open(id: number) {
    if (!store || id === threadId) return setRailOpen(false);
    stopAndClear();
    // Only the last click counts when several opens are in flight.
    const ticket = ++opening.current;
    let thread;
    try {
      thread = await store.get(id);
    } catch (err) {
      if (ticket === opening.current) toast({ kind: "error", title: "Couldn't open that chat", detail: (err as Error).message });
      return;
    }
    if (ticket !== opening.current) return;
    if (!thread) {
      toast({ kind: "error", title: "That chat is no longer available" });
      setThreads((ts) => ts.filter((t) => t.id !== id));
      return;
    }
    conversation.current = fresh(id);
    setMessages(thread.messages.map((m) => ({ ...m, id: nextId.current++ })));
    setThreadId(id);
    setRailOpen(false);
  }

  async function remove(id: number) {
    if (!store) return;
    try {
      await store.remove(id);
      setThreads((ts) => ts.filter((t) => t.id !== id));
      if (id === threadId) newChat();
    } catch {
      toast({ kind: "error", title: "Couldn't delete that chat" });
    }
  }

  async function attach(files: FileList | File[] | null) {
    const list = Array.from(files ?? []).filter((f) => /^image\/(png|jpeg|webp|gif)$/.test(f.type));
    if (!list.length) return;
    const room = MAX_IMAGES - images.length;
    if (room <= 0) return toast({ kind: "info", title: `Up to ${MAX_IMAGES} images per message` });
    for (const file of list.slice(0, room)) {
      try {
        const url = await imageToDataUrl(file);
        setImages((imgs) => (imgs.length < MAX_IMAGES ? [...imgs, url] : imgs));
      } catch (err) {
        toast({ kind: "error", title: "Couldn't attach that image", detail: (err as Error).message });
      }
    }
  }

  const empty = messages.length === 0;
  const canSend = (input.trim().length > 0 || images.length > 0) && !streaming;

  const rail = (
    <nav aria-label="Conversations" className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-1.5 p-3">
        <button type="button" onClick={newChat} className="vt-btn vt-btn-quiet flex-1 justify-start">
          <PlusIcon size={15} /> New chat
        </button>
        <button type="button" onClick={() => setRailHidden(true)} aria-label="Collapse history" title="Collapse history"
          className="hidden h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink md:grid">
          <PanelIcon size={16} />
        </button>
      </div>
      <p className="px-4 pb-1.5 text-xs font-medium text-subtle">Recent</p>
      <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {threads.length === 0 && <li className="px-2 py-2 text-xs text-subtle">Your conversations will show up here.</li>}
        {threads.map((t) => (
          <li key={t.id} className="group relative">
            <button type="button" onClick={() => open(t.id)} aria-current={t.id === threadId ? "true" : undefined}
              className={`flex w-full items-center gap-2 rounded-lg py-2 pl-2.5 pr-8 text-left text-sm transition ${
                t.id === threadId ? "bg-accent/12 text-ink" : "text-muted hover:bg-sunken hover:text-ink"}`}>
              <ChatIcon size={14} className="shrink-0 opacity-70" />
              <span className="min-w-0 flex-1 truncate">{t.title}</span>
              <span className="shrink-0 text-[11px] text-subtle group-focus-within:invisible group-hover:invisible [@media(hover:none)]:invisible">{when(t.updated_at)}</span>
            </button>
            <button type="button" onClick={() => remove(t.id)} aria-label={`Delete "${t.title}"`}
              className="absolute right-1.5 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded-md text-subtle opacity-0 transition hover:bg-line hover:text-ink focus-visible:opacity-100 group-focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
              <TrashIcon size={13} />
            </button>
          </li>
        ))}
      </ul>
      {store?.where === "browser" && (
        <p className="border-t border-line px-4 py-2.5 text-[11px] text-subtle">Demo mode: chats are saved in this browser.</p>
      )}
    </nav>
  );

  return (
    // Exactly the room left under the top bars and above the main padding, so the page itself never scrolls;
    // only the conversation does. (Phone: 181px above, 24px below. Desktop: 72px above, 36px below.)
    <div className="flex h-[calc(100dvh-205px)] min-h-[480px] flex-col md:h-[calc(100dvh-108px)]">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-[1.65rem] font-semibold leading-tight tracking-tight">Ask Verytas</h1>
        <div className="flex items-center gap-2 md:hidden">
          <button type="button" onClick={() => setRailOpen(true)} className="vt-btn vt-btn-quiet"><HistoryIcon size={15} /> History</button>
          <button type="button" onClick={newChat} aria-label="New chat" className="vt-btn vt-btn-quiet px-2.5"><PlusIcon size={15} /></button>
        </div>
      </div>

      <div className="vt-card flex min-h-0 flex-1 overflow-hidden">
        {railHidden ? (
          <div className="hidden w-14 shrink-0 flex-col items-center gap-1.5 border-r border-line py-3 md:flex">
            <button type="button" onClick={() => setRailHidden(false)} aria-label="Show history" title="Show history"
              className="grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
              <PanelIcon size={16} />
            </button>
            <button type="button" onClick={newChat} aria-label="New chat" title="New chat"
              className="grid h-9 w-9 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
              <PlusIcon size={16} />
            </button>
          </div>
        ) : (
          <aside className="vt-rail hidden w-64 shrink-0 border-r border-line md:block">{rail}</aside>
        )}
        {railOpen && <div className="md:hidden"><Drawer label="History" onClose={() => setRailOpen(false)}>{rail}</Drawer></div>}

        <div className="flex min-w-0 flex-1 flex-col">
          <p className="sr-only" role="status" aria-live="polite">{status}</p>
          <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
            {empty ? (
              <div className="vt-stagger mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-6 py-10 text-center">
                <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
                  <SparkIcon size={20} className="text-accent" aria-hidden />What would you like to know?
                </h2>
                <p className="mt-1.5 text-sm text-muted">Ask about your own content or the workspace. Answers come as charts and tables.</p>
                <div className="mt-8 grid w-full gap-2.5 sm:grid-cols-2">
                  {STARTERS[side === "manager" ? "manager" : "creator"].map((st) => (
                    <button key={st.label} type="button" onClick={() => send(st.prompt)}
                      className="vt-lift group flex items-center justify-between gap-3 rounded-xl border border-line bg-raised px-4 py-3 text-left text-sm transition hover:text-ink">
                      {st.label}
                      <ArrowRightIcon size={14} aria-hidden className="shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-accent" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6 md:px-6">
                {messages.map((m, i) => (
                  <ChatMessage key={m.id} message={m} onAction={onAction}
                    streaming={streaming && i === messages.length - 1 && m.role === "assistant"} />
                ))}
                <div ref={end} />
              </div>
            )}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); if (canSend) void send(input, images); }}
            className="border-t border-line p-3 md:p-4"
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); void attach(e.dataTransfer.files); }}>
            <div className="mx-auto max-w-3xl rounded-2xl border border-line bg-raised p-2 transition focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/15">
              {images.length > 0 && (
                <ul className="flex flex-wrap gap-2 px-1 pb-2 pt-1">
                  {images.map((src, i) => (
                    <li key={i} className="vt-pop relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={src} alt={`Attachment ${i + 1}`} className="h-14 w-14 rounded-lg border border-line object-cover" />
                      <button type="button" onClick={() => setImages((imgs) => imgs.filter((_, k) => k !== i))}
                        aria-label={`Remove attachment ${i + 1}`}
                        className="absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full border border-line bg-raised text-muted shadow-[var(--vt-shadow)] hover:text-ink">
                        <CloseIcon size={11} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex items-end gap-1.5">
                <button type="button" onClick={() => picker.current?.click()} aria-label="Attach images"
                  disabled={images.length >= MAX_IMAGES}
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-sunken hover:text-ink disabled:opacity-40">
                  <PaperclipIcon size={17} />
                </button>
                <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple className="sr-only"
                  tabIndex={-1} onChange={(e) => { void attach(e.target.files); e.target.value = ""; }} />
                <textarea ref={box} value={input} rows={1} maxLength={4000} placeholder="Ask about your content, reviews or rules"
                  aria-label="Your question"
                  onChange={(e) => {
                    setInput(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
                  }}
                  onPaste={(e) => {
                    const files = Array.from(e.clipboardData.files);
                    if (files.length) { e.preventDefault(); void attach(files); }
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      if (canSend) void send(input, images);
                    }
                  }}
                  className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-1.5 py-1.5 text-sm leading-6 outline-none placeholder:text-subtle" />
                {streaming ? (
                  <button type="button" onClick={() => abort.current?.abort()} aria-label="Stop"
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink transition hover:bg-line">
                    <span aria-hidden className="h-3 w-3 rounded-[3px] bg-current" />
                  </button>
                ) : (
                  <button type="submit" disabled={!canSend} aria-label="Send"
                    className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl transition active:scale-95 ${canSend
                      ? "bg-accent text-accent-ink hover:brightness-110" : "bg-sunken text-subtle"}`}>
                    <ArrowUpIcon size={17} />
                  </button>
                )}
              </div>
            </div>
            <p className="mx-auto mt-2 max-w-3xl px-1 text-[11px] text-subtle">
              Answers are written by an AI model from your workspace&apos;s data and can be wrong.{" "}
              <AiInfoButton className="underline underline-offset-2 hover:text-ink" />.
              Images are kept with the chat; the current model can&apos;t read them yet.
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}

function ChatMessage({ message: m, streaming, onAction }: {
  message: Message;
  streaming: boolean;
  onAction: (e: ActionEvent) => void;
}) {
  const [parsed, setParsed] = useState<ParseResult | null>(null);

  if (m.role === "user") {
    return (
      <div className="vt-pop flex flex-col items-end gap-2">
        {m.images && m.images.length > 0 && (
          <div className="flex flex-wrap justify-end gap-2">
            {m.images.map((src, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={i} src={src} alt={`Attached image ${i + 1}`} className="h-24 max-w-40 rounded-xl border border-line object-cover" />
            ))}
          </div>
        )}
        {m.content && (
          <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-sunken px-4 py-2.5 text-sm leading-6">{m.content}</p>
        )}
      </div>
    );
  }
  // A reply that isn't OpenUI Lang (or failed to parse) is still shown, as text.
  const plain = !streaming && m.content && !parsed?.root;
  return (
    <div className="vt-pop flex gap-3">
      <Logo size={26} className="mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1 text-sm leading-6">
        {m.error ? (
          <p className="rounded-xl bg-[var(--vt-blocker-bg)] px-3 py-2 text-[var(--vt-blocker)]">{m.content}</p>
        ) : m.note && !m.content ? (
          <p className="py-1.5 text-muted">{m.note}</p>
        ) : !m.content ? (
          <span className="vt-typing inline-flex gap-1 py-2" aria-label="Thinking">
            <span className="h-1.5 w-1.5 rounded-full bg-subtle" /><span className="h-1.5 w-1.5 rounded-full bg-subtle" />
            <span className="h-1.5 w-1.5 rounded-full bg-subtle" />
          </span>
        ) : (
          <>
            <div className={plain ? "hidden" : undefined}>
              <Renderer response={m.content} library={openuiLibrary} isStreaming={streaming} onAction={onAction}
                onParseResult={setParsed} />
            </div>
            {plain && <p className="whitespace-pre-wrap">{m.content}</p>}
          </>
        )}
      </div>
    </div>
  );
}

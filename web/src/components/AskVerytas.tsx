"use client";

import { type ActionEvent, type ParseResult, Renderer } from "@openuidev/react-lang";
import { openuiLibrary } from "@openuidev/react-ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpIcon, PlusIcon, SparkIcon } from "./Icons";

// Ask Verytas, full page. The model answers in OpenUI Lang (charts, tables,
// callouts) streamed from /api/chat; OpenUI's renderer draws it with the app's
// own theme. The conversation lives in this page only.

type Message = { id: number; role: "user" | "assistant"; content: string; error?: boolean; note?: string };

const STARTERS = [
  { label: "Which rules get overridden most?", prompt: "Which rules do reviewers override most, and why might that be?" },
  { label: "How did blockers trend this month?", prompt: "Show how blockers trended over the last 30 days." },
  { label: "What should we clarify first?", prompt: "Which guideline should the brand team clarify first, based on the data?" },
  { label: "Where do problems come from?", prompt: "Break down findings by category and tell me the biggest source of problems." },
];

/** Reads an OpenAI-style SSE stream, calling `onText` with each content delta.
 * Lines are only parsed once complete; an error payload from upstream throws. */
async function readStream(res: Response, onText: (t: string) => void) {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const handle = (line: string) => {
    const data = line.startsWith("data:") ? line.slice(5).trim() : "";
    if (!data || data === "[DONE]") return;
    let event: { error?: { message?: string } | string; choices?: { delta?: { content?: unknown } }[] };
    try {
      event = JSON.parse(data);
    } catch {
      return; // not JSON (a comment or keep-alive); complete lines are never split
    }
    if (event.error) throw new Error(typeof event.error === "string" ? event.error : event.error.message ?? "The model failed.");
    const delta = event.choices?.[0]?.delta?.content;
    if (typeof delta === "string") onText(delta);
  };
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = done ? "" : lines.pop() ?? "";
    lines.forEach(handle);
    if (done) break;
  }
}

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

export function AskVerytas() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const end = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const [status, setStatus] = useState("");

  // Follow the answer only while the reader is at the bottom; scrolling up to
  // read something earlier is never fought.
  useEffect(() => {
    const el = scroller.current;
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 120) end.current?.scrollIntoView({ block: "end" });
  }, [messages]);
  useEffect(() => () => abort.current?.abort(), []);

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || streaming) return;
    const history = [...messages.filter((m) => !m.error), { id: nextId.current++, role: "user" as const, content: question }];
    const answerId = nextId.current++;
    setMessages([...history, { id: answerId, role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);
    setStatus("Verytas is answering");
    const write = (fn: (m: Message) => Message) => setMessages((all) => all.map((m) => (m.id === answerId ? fn(m) : m)));
    const controller = new AbortController();
    abort.current = controller;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history.map(({ role, content }) => ({ role, content })) }),
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
    }
  }, [messages, streaming]);

  const onAction = useCallback((event: ActionEvent) => {
    if (event.type === "continue_conversation") void send(event.humanFriendlyMessage);
    else if (event.type === "open_url") {
      const url = safeUrl(event.params?.url);
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    }
  }, [send]);

  function reset() {
    abort.current?.abort();
    abort.current = null;
    setStreaming(false);
    setMessages([]);
    setInput("");
    box.current?.focus();
  }

  const empty = messages.length === 0;

  return (
    <div className="flex h-[calc(100dvh-9.5rem)] min-h-[520px] flex-col md:h-[calc(100dvh-4.5rem)]">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-[1.65rem] font-semibold leading-tight tracking-tight">Ask Verytas</h1>
        {!empty && (
          <button type="button" onClick={reset} className="vt-btn vt-btn-quiet">
            <PlusIcon size={15} /> New chat
          </button>
        )}
      </div>

      <div className="vt-card flex min-h-0 flex-1 flex-col overflow-hidden">
        <p className="sr-only" role="status" aria-live="polite">{status}</p>
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          {empty ? (
            <div className="vt-stagger mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-6 py-10 text-center">
              <span aria-hidden className="vt-mark grid h-12 w-12 place-items-center rounded-2xl"><SparkIcon size={22} /></span>
              <h2 className="mt-5 text-xl font-semibold tracking-tight">What would you like to know?</h2>
              <p className="mt-1.5 text-sm text-muted">Answers come from your workspace data, as charts and tables.</p>
              <div className="mt-8 grid w-full gap-2.5 sm:grid-cols-2">
                {STARTERS.map((s) => (
                  <button key={s.label} type="button" onClick={() => send(s.prompt)}
                    className="vt-lift rounded-xl border border-line bg-raised px-4 py-3 text-left text-sm transition hover:text-ink">
                    {s.label}
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

        <form onSubmit={(e) => { e.preventDefault(); void send(input); }} className="border-t border-line p-3 md:p-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-line bg-raised p-2 transition focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/15">
            <textarea ref={box} value={input} rows={1} maxLength={4000} placeholder="Ask about reviews, rules or findings"
              aria-label="Your question"
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-6 outline-none placeholder:text-subtle" />
            {streaming ? (
              <button type="button" onClick={() => abort.current?.abort()} aria-label="Stop"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-sunken text-ink transition hover:bg-line">
                <span aria-hidden className="h-3 w-3 rounded-[3px] bg-current" />
              </button>
            ) : (
              <button type="submit" disabled={!input.trim()} aria-label="Send"
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl transition active:scale-95 ${input.trim()
                  ? "bg-accent text-accent-ink hover:brightness-110" : "bg-sunken text-subtle"}`}>
                <ArrowUpIcon size={17} />
              </button>
            )}
          </div>
        </form>
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
      <div className="vt-pop flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-sunken px-4 py-2.5 text-sm leading-6">{m.content}</p>
      </div>
    );
  }
  // A reply that isn't OpenUI Lang (or failed to parse) is still shown, as text.
  const plain = !streaming && m.content && !parsed?.root;
  return (
    <div className="vt-pop flex gap-3">
      <span aria-hidden className="vt-mark mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg"><SparkIcon size={14} /></span>
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

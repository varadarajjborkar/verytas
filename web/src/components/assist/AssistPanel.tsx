"use client";

import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type AssistKind, type Brief, NEXT_LABEL, readable } from "@/lib/assist";
import { readStream } from "@/lib/sse";
import { useModalFocus } from "../Drawer";
import { ArrowUpIcon, CloseIcon, RefreshIcon, SparkIcon } from "../Icons";
import { RuleCode } from "../ui";

type Phase = "loading" | "ready" | "error";
type Turn = { role: "user" | "assistant"; content: string; failed?: boolean };

const STARTERS = ["Why was this flagged?", "What did the creator say?", "What changed since the last round?", "Is the legal concern real?"];
const STARTERS_ESCALATION = ["Is the creator right?", "Why was this flagged?", "What would you check first?", "What changed since the last round?"];

async function post(body: Record<string, unknown>, signal: AbortSignal): Promise<Response> {
  return fetch("/api/assist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
}

async function errorOf(res: Response): Promise<string> {
  const data = (await res.json().catch(() => null)) as { error?: string } | null;
  return data?.error ?? "Something went wrong. Try again in a moment.";
}

/**
 * The manager's side panel for one piece or escalation: a short brief at the top, and a chat below it that
 * is grounded in that one item only. The server builds and redacts what the model sees (see api/assist);
 * the panel never holds the dossier, only the brief and the conversation.
 */
export function AssistPanel({ kind, id, title, onClose }: { kind: AssistKind; id: number; title: string; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useModalFocus(panel, onClose);

  const [phase, setPhase] = useState<Phase>("loading");
  const [brief, setBrief] = useState<Brief | null>(null);
  const [fallback, setFallback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const briefAbort = useRef<AbortController | null>(null);
  const chatAbort = useRef<AbortController | null>(null);

  // Only the state changes after the request; callers that need "loading" set it first (see refresh).
  const fetchBrief = useCallback(async () => {
    briefAbort.current?.abort();
    const ctl = new AbortController();
    briefAbort.current = ctl;
    try {
      const res = await post({ kind, id, mode: "summary" }, ctl.signal);
      if (!res.ok) throw new Error(await errorOf(res));
      const data = (await res.json()) as { brief: Brief | null; text: string | null };
      setBrief(data.brief);
      setFallback(data.text);
      setError(null);
      setPhase("ready");
    } catch (err) {
      if (ctl.signal.aborted) return;
      setError(err instanceof TypeError ? "Couldn't reach Verytas. Check the connection and try again." : (err as Error).message);
      setPhase("error");
    }
  }, [kind, id]);

  useEffect(() => {
    // The request is awaited before any state changes; the rule can't see through async functions.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchBrief();
    return () => { briefAbort.current?.abort(); chatAbort.current?.abort(); };
  }, [fetchBrief]);

  function refresh() {
    setPhase("loading");
    void fetchBrief();
  }

  // Keep the newest words in view while an answer streams in.
  useEffect(() => {
    const el = scroller.current;
    if (el && turns.length) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [turns]);

  async function send(text: string) {
    const question = text.trim();
    if (!question || sending) return;
    const history: Turn[] = [...turns.filter((t) => !t.failed), { role: "user", content: question }];
    setTurns([...history, { role: "assistant", content: "" }]);
    setDraft("");
    setSending(true);
    const ctl = new AbortController();
    chatAbort.current = ctl;
    const write = (fn: (t: Turn) => Turn) => setTurns((all) => all.map((t, i) => (i === all.length - 1 ? fn(t) : t)));
    try {
      const res = await post({ kind, id, mode: "chat", messages: history.map(({ role, content }) => ({ role, content })) }, ctl.signal);
      if (!res.ok) throw new Error(await errorOf(res));
      await readStream(res, (t) => write((m) => ({ ...m, content: m.content + t })));
      write((m) => (m.content.trim() ? m : { ...m, content: "I couldn't come up with an answer. Try asking it another way.", failed: true }));
    } catch (err) {
      if (ctl.signal.aborted) return;
      const message = err instanceof TypeError ? "Couldn't reach Verytas. Check the connection and try again." : (err as Error).message;
      write((m) => ({ ...m, content: m.content ? `${m.content}\n\n(The answer was cut short: ${message})` : message, failed: true }));
    } finally {
      setSending(false);
    }
  }

  const starters = kind === "escalation" ? STARTERS_ESCALATION : STARTERS;

  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="vt-pop absolute inset-y-0 right-0 flex w-full flex-col overflow-hidden border-l border-line bg-raised shadow-[var(--vt-shadow-pop)] sm:inset-y-3 sm:right-3 sm:w-[min(32rem,calc(100vw-1.5rem))] sm:rounded-2xl sm:border">
        <div className="flex items-start gap-3 border-b border-line px-4 py-3.5 sm:px-5">
          <span aria-hidden className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-sunken text-accent"><SparkIcon size={16} /></span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-sm font-semibold">{kind === "escalation" ? "Escalation brief" : "Summary"}</h2>
            <p className="truncate text-xs text-muted" title={readable(title)}>{readable(title)}</p>
          </div>
          <button type="button" onClick={refresh} disabled={phase === "loading"} title="Write the summary again from the latest data"
            className="vt-btn vt-btn-quiet h-8 px-2.5 text-xs">
            <RefreshIcon size={13} className={phase === "loading" ? "animate-spin" : ""} />
            <span className="hidden sm:inline">Refresh summary</span>
            <span className="sm:hidden">Refresh</span>
          </button>
          <button type="button" onClick={onClose} aria-label="Close summary"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink"><CloseIcon size={16} /></button>
        </div>

        <div ref={scroller} className="vt-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-5">
          {phase === "loading" ? <BriefSkeleton />
            : phase === "error" ? (
              <div role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3.5 text-sm">
                <p className="font-medium text-[var(--vt-blocker)]">Couldn&apos;t write the summary</p>
                <p className="mt-1 text-[13px] leading-5 text-muted">{error}</p>
                <button type="button" onClick={refresh} className="vt-btn vt-btn-quiet mt-3">Try again</button>
              </div>
            ) : brief ? <BriefView brief={brief} />
              : <FallbackView text={fallback ?? ""} />}

          <section aria-label="Ask about this item" className="mt-6 border-t border-line pt-5">
            <h3 className="text-[11px] font-medium uppercase tracking-wide text-subtle">Ask about this item</h3>
            {turns.length === 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {starters.map((s) => (
                  <button key={s} type="button" disabled={sending || phase === "loading"} onClick={() => void send(s)}
                    className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50">
                    {s}
                  </button>
                ))}
              </div>
            ) : (
              <ul className="mt-3 flex flex-col gap-3" aria-live="polite">
                {turns.map((t, i) => (
                  <li key={i} className={t.role === "user" ? "ml-8 self-end rounded-xl bg-sunken px-3 py-2 text-[13px] leading-5"
                    : `text-[13px] leading-6 ${t.failed ? "text-[var(--vt-blocker)]" : ""}`}>
                    {t.role === "assistant" && !t.content ? <Thinking /> : <Prose text={t.content} />}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <form className="border-t border-line px-4 py-3 sm:px-5"
          onSubmit={(e) => { e.preventDefault(); void send(draft); }}>
          <div className="flex items-end gap-2">
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={1} maxLength={2000}
              aria-label="Your question about this item" placeholder="Ask about this item…"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(draft); } }}
              className="vt-input max-h-32 min-h-10 flex-1 resize-none py-2.5 text-[13px]" />
            <button type="submit" disabled={sending || !draft.trim()} aria-label="Send question"
              className="vt-btn vt-btn-primary h-10 w-10 shrink-0 px-0"><ArrowUpIcon size={16} /></button>
          </div>
          <p className="mt-2 text-[11px] leading-4 text-subtle">
            AI-assisted, from this item&apos;s record only. It can be wrong: you decide.
          </p>
        </form>
      </div>
    </div>,
    document.body,
  );
}

function BriefSkeleton() {
  return (
    <div aria-busy="true" role="status" className="flex animate-pulse flex-col gap-4">
      <span className="sr-only">Reading this item and writing the summary</span>
      <div className="h-16 rounded-xl bg-sunken" />
      <div className="h-24 rounded-xl bg-sunken" />
      <div className="h-4 w-2/3 rounded bg-sunken" />
      <div className="h-4 w-1/2 rounded bg-sunken" />
      <div className="h-20 rounded-xl bg-sunken" />
    </div>
  );
}

function Thinking() {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-xs text-muted">
      <span aria-hidden className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      Reading the record…
    </span>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wide text-subtle">{label}</h3>
      {children}
    </section>
  );
}

function BriefView({ brief }: { brief: Brief }) {
  const step = brief.suggested_next_step;
  return (
    <div className="flex flex-col gap-5">
      <p className="text-[15px] font-medium leading-6">{readable(brief.tldr)}</p>

      {/* Set apart on purpose: it is a suggestion to weigh, never an instruction or a decision. */}
      {(step.action || step.reason) && (
        <section aria-label="Suggested next step"
          className="rounded-xl border border-[color-mix(in_srgb,var(--vt-accent)_35%,var(--vt-line))] bg-[color-mix(in_srgb,var(--vt-accent)_6%,var(--vt-raised))] p-3.5">
          <p className="flex items-center justify-between gap-2 text-[11px] font-medium uppercase tracking-wide text-accent">
            <span>Suggested next step</span><span className="normal-case tracking-normal text-muted">A suggestion. You decide.</span>
          </p>
          {step.action && <p className="mt-1.5 text-sm font-semibold">{NEXT_LABEL[step.action]}</p>}
          {step.reason && <p className="mt-1 text-[13px] leading-5 text-muted">{readable(step.reason)}</p>}
        </section>
      )}

      <Section label="Stopping approval">
        {brief.blocking.length === 0 ? (
          <p className="rounded-lg bg-[var(--vt-ok-bg)] px-3 py-2 text-[13px] font-medium text-[var(--vt-ok)]">Nothing here blocks approval.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {brief.blocking.map((b, i) => (
              <li key={i} className="rounded-lg border-l-2 border-[var(--vt-blocker)] bg-[var(--vt-blocker-bg)] px-3 py-2.5">
                {b.rule && <RuleCode code={b.rule} />}
                <p className="text-[13px] font-medium leading-5">{readable(b.issue)}</p>
                {b.why && <p className="mt-0.5 text-xs leading-5 text-muted">{readable(b.why)}</p>}
              </li>
            ))}
          </ul>
        )}
      </Section>

      {brief.minor.length > 0 && (
        <Section label="Smaller issues">
          <ul className="flex flex-col gap-1.5">
            {brief.minor.map((m, i) => (
              <li key={i} className="flex items-baseline gap-2 text-[13px] leading-5">
                <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--vt-warning)]" />
                <span>{m.rule && <RuleCode code={m.rule} className="mr-1.5 inline" />}{readable(m.issue)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {brief.creator_side && <Section label="The creator's side"><p className="text-[13px] leading-6">{readable(brief.creator_side)}</p></Section>}

      {brief.history.length > 0 && (
        <Section label="How it got here">
          <ol className="flex flex-col gap-1.5 border-l border-line pl-4">
            {brief.history.map((h, i) => <li key={i} className="text-[13px] leading-5 text-muted">{readable(h)}</li>)}
          </ol>
        </Section>
      )}

      {brief.questions_to_ask.length > 0 && (
        <Section label="Worth asking">
          <ul className="flex list-disc flex-col gap-1 pl-4 text-[13px] leading-5">
            {brief.questions_to_ask.map((q, i) => <li key={i}>{readable(q)}</li>)}
          </ul>
        </Section>
      )}

      {brief.risk_if_published && (
        <Section label="If it goes out as it is"><p className="text-[13px] leading-6">{readable(brief.risk_if_published)}</p></Section>
      )}
    </div>
  );
}

/** The model didn't return the structure asked for; its words are still shown, plainly. */
function FallbackView({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="rounded-lg bg-sunken px-3 py-2 text-xs text-muted">This summary came back as plain text rather than sections.</p>
      <Prose text={text} />
    </div>
  );
}

/** Model text as paragraphs and simple lists. Never HTML: the words are shown, not interpreted. */
function Prose({ text }: { text: string }) {
  const blocks = readable(text).replace(/\*\*/g, "").trim().split(/\n{2,}/);
  return (
    <div className="flex flex-col gap-2">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        return lines.every((l) => /^\s*[-*]\s+/.test(l)) ? (
          <ul key={i} className="list-disc pl-4">{lines.map((l, j) => <li key={j}>{l.replace(/^\s*[-*]\s+/, "")}</li>)}</ul>
        ) : <p key={i} className="whitespace-pre-wrap">{block}</p>;
      })}
    </div>
  );
}

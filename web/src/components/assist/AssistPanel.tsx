"use client";

import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type AssistKind, type Brief, NEXT_LABEL, plainText, readable, splitFollowUps } from "@/lib/assist";
import { readStream } from "@/lib/sse";
import { useModalFocus } from "../Drawer";
import { ArrowUpIcon, ChevronIcon, CloseIcon, RefreshIcon } from "../Icons";
import { INKI, InkiIcon } from "../Inki";

type Phase = "loading" | "ready" | "error";
type Turn = { role: "user" | "assistant"; content: string; failed?: boolean };


async function post(body: Record<string, unknown>, signal: AbortSignal): Promise<Response> {
  return fetch("/api/assist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
}

async function errorOf(res: Response): Promise<string> {
  const data = (await res.json().catch(() => null)) as { error?: string } | null;
  return data?.error ?? "Something went wrong. Try again in a moment.";
}

/**
 * The manager's side panel for one piece or escalation, in Inki's voice: Inki's short brief at the top, and a
 * chat with Inki below it that is grounded in that one item only. The server builds and redacts what the model sees (see api/assist);
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

  // One place for "what to ask next": first the brief's questions about this item, then whatever the latest
  // answer suggests, never one already asked. Written by the model from the item's own data, in the same call.
  const asked = new Set(turns.filter((t) => t.role === "user").map((t) => t.content.trim().toLowerCase()));
  const latest = [...turns].reverse().find((t) => t.role === "assistant" && !t.failed && t.content);
  const fromAnswer = latest && !sending ? splitFollowUps(latest.content).followUps.map(plainText) : [];
  // The model can repeat itself; one button per distinct question keeps the list (and its keys) unique.
  const shownAlready = new Set(asked);
  const suggestions = (fromAnswer.length ? fromAnswer : brief?.follow_ups ?? []).filter((q) => {
    const key = q.trim().toLowerCase();
    if (shownAlready.has(key)) return false;
    shownAlready.add(key);
    return true;
  }).slice(0, 3);
  // Announced once, when the answer is complete: a live region over the streaming list would read the
  // growing text again on every chunk.
  const announced = latest && !sending ? plainText(splitFollowUps(latest.content).body) : "";

  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="vt-pop absolute inset-y-0 right-0 flex w-full flex-col overflow-hidden border-l border-line bg-raised shadow-[var(--vt-shadow-pop)] sm:inset-y-3 sm:right-3 sm:w-[min(32rem,calc(100vw-1.5rem))] sm:rounded-2xl sm:border">
        <div className="flex items-start gap-3 border-b border-line px-4 py-3.5 sm:px-5">
          <InkiIcon size={32} className="shrink-0" />
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-sm font-semibold">{INKI}&apos;s {kind === "escalation" ? "brief on this escalation" : "summary"}</h2>
            <p className="truncate text-xs text-muted" title={readable(title)}>{readable(title)}</p>
          </div>
          <button type="button" onClick={refresh} disabled={phase === "loading"} title={`${INKI} writes the summary again from the latest data`}
            className="vt-btn vt-btn-quiet vt-btn-sm">
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
                <p className="font-medium text-[var(--vt-blocker)]">{INKI} couldn&apos;t write the summary</p>
                <p className="mt-1 text-[13px] leading-5 text-muted">{error}</p>
                <button type="button" onClick={refresh} className="vt-btn vt-btn-quiet mt-3">Try again</button>
              </div>
            ) : (
              // Inki's words sit in Inki's tinted card, as its answers do in a conversation.
              <div className="vt-pop rounded-2xl rounded-tl-md border border-accent/25 bg-accent/[0.07] px-4 py-3.5">
                {brief ? <BriefView brief={brief} /> : <FallbackView text={fallback ?? ""} />}
              </div>
            )}

          <section aria-label={`Ask ${INKI} about this item`} className="mt-6 border-t border-line pt-5">
            <h3 className="text-[11px] font-medium uppercase tracking-wide text-subtle">Ask {INKI} about this item</h3>
            <p role="status" className="sr-only">{announced}</p>
            {turns.length > 0 && (
              <ul className="mt-3 flex flex-col gap-3">
                {turns.map((t, i) => t.role === "user" ? (
                  <li key={i} className="ml-8 self-end rounded-2xl rounded-br-md bg-sunken px-3 py-2 text-[13px] leading-5">
                    <Prose text={t.content} />
                  </li>
                ) : (
                  <li key={i} className="flex gap-2.5">
                    <InkiIcon size={24} className="mt-0.5 shrink-0" />
                    <div className={`min-w-0 flex-1 text-[13px] leading-6 ${t.failed ? "text-[var(--vt-blocker)]" : ""}`}>
                      {!t.content ? <Thinking /> : <Prose text={plainText(splitFollowUps(t.content).body)} />}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {phase === "loading" ? (
              <div aria-hidden className="mt-3 flex animate-pulse flex-wrap gap-2">
                {[44, 36, 52].map((w) => <span key={w} className="h-7 rounded-full bg-sunken" style={{ width: `${w}%` }} />)}
              </div>
            ) : suggestions.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2" aria-label="Suggested questions">
                {suggestions.map((s) => (
                  <button key={s} type="button" disabled={sending} onClick={() => void send(s)}
                    className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-xs text-muted transition hover:border-line-strong hover:text-ink disabled:opacity-50">
                    {s}
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>

        <form className="border-t border-line px-4 py-3 sm:px-5"
          onSubmit={(e) => { e.preventDefault(); void send(draft); }}>
          <div className="flex items-end gap-2">
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={1} maxLength={2000}
              aria-label={`Your question for ${INKI} about this item`} placeholder={`Ask ${INKI} about this item…`}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(draft); } }}
              className="vt-input max-h-32 min-h-10 flex-1 resize-none py-2.5 text-[13px]" />
            <button type="submit" disabled={sending || !draft.trim()} aria-label="Send question"
              className="vt-btn vt-btn-primary h-10 w-10 shrink-0 px-0"><ArrowUpIcon size={16} /></button>
          </div>
          <p className="mt-2 text-[11px] leading-4 text-subtle">
            {INKI} is AI and reads this item&apos;s record only. It can be wrong: you decide.
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
      <span className="sr-only">{INKI} is reading this item and writing the summary</span>
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
    <span role="status" className="inline-flex items-center gap-2 py-1 text-xs text-muted">
      {INKI} is reading the record
      <span aria-hidden className="vt-typing inline-flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-subtle" /><span className="h-1.5 w-1.5 rounded-full bg-subtle" />
        <span className="h-1.5 w-1.5 rounded-full bg-subtle" />
      </span>
    </span>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-subtle">{label}</h3>
      {children}
    </section>
  );
}

/** A short numbered list in ink and grey only: the words carry it, not colour. */
function Points({ items }: { items: { text: string; note?: string }[] }) {
  return (
    <ol className="flex flex-col gap-2">
      {items.map((p, i) => (
        <li key={i} className="flex gap-2.5 text-[13px] leading-5">
          <span aria-hidden className="w-3 shrink-0 text-right tabular-nums text-subtle">{i + 1}</span>
          <span>{readable(p.text)}{p.note && <span className="block text-xs text-muted">{readable(p.note)}</span>}</span>
        </li>
      ))}
    </ol>
  );
}

/**
 * The brief, read top to bottom in a few seconds: one sentence, the suggested step, what must change and what
 * is worth a look. The rest (the creator's side, how it got here, the risk) is folded away, one click down.
 */
function BriefView({ brief }: { brief: Brief }) {
  const step = brief.suggested_next_step;
  const more = Boolean(brief.creator_side || brief.history.length || brief.ask_creator.length || brief.risk_if_published);
  return (
    <div className="flex flex-col gap-5">
      <p className="text-[15px] leading-6">{readable(brief.tldr)}</p>

      {/* A suggestion to weigh, never a decision: worded and placed as one. */}
      {(step.action || step.reason) && (
        <Section label="Suggested next step">
          {step.action && <p className="text-sm font-medium">{NEXT_LABEL[step.action]}</p>}
          {step.reason && <p className="text-[13px] leading-5 text-muted">{readable(step.reason)}</p>}
        </Section>
      )}

      <Section label="Must change">
        {brief.blocking.length === 0
          ? <p className="text-[13px] leading-5 text-muted">Nothing must change before approval.</p>
          : <Points items={brief.blocking.map((b) => ({ text: b.issue, note: b.why }))} />}
      </Section>

      {brief.minor.length > 0 && (
        <Section label="Worth a look"><Points items={brief.minor.map((m) => ({ text: m.issue }))} /></Section>
      )}

      {more && (
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs font-medium text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
            More detail<ChevronIcon size={13} className="transition-transform duration-200 group-open:rotate-180" />
          </summary>
          <dl className="mt-3 flex flex-col gap-3 text-[13px] leading-5">
            {brief.creator_side && <Detail term="The creator says">{readable(brief.creator_side)}</Detail>}
            {brief.history.length > 0 && <Detail term="So far">{brief.history.map((h, i) => <span key={i} className="block">{readable(h)}</span>)}</Detail>}
            {brief.ask_creator.length > 0 && <Detail term="Ask the creator for">{brief.ask_creator.map((q, i) => <span key={i} className="block">{readable(q)}</span>)}</Detail>}
            {brief.risk_if_published && <Detail term="If it goes out as it is">{readable(brief.risk_if_published)}</Detail>}
          </dl>
        </details>
      )}
    </div>
  );
}

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-subtle">{term}</dt>
      <dd>{children}</dd>
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

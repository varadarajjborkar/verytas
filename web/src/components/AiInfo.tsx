"use client";

import { type ReactNode, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useModalFocus } from "./Drawer";
import { CheckIcon, CloseIcon, ImageIcon, ReviewIcon, ShieldIcon, SparkIcon, UsersIcon } from "./Icons";

/**
 * The AI disclosure the brief asks for, reachable from every screen of both apps. It opens over the page
 * like Settings, so reading it never loses the reader's place; /ai shows the same content for direct links.
 * Kept short and visual on purpose: the flow says who does what, the three columns say where content goes.
 */
export function AiInfoButton({ children = "How AI is used", className = "" }: { children?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" className={className}>{children}</button>
      {open && <AiInfoDialog onClose={() => setOpen(false)} />}
    </>
  );
}

function AiInfoDialog({ onClose }: { onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useModalFocus(panel, onClose);

  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="vt-pop relative flex max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold">How Verytas uses AI</h2>
            <p className="mt-0.5 text-[13px] text-muted">AI reads and suggests. People decide.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close"
            className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
            <CloseIcon size={16} />
          </button>
        </div>
        <div className="vt-scroll overflow-y-auto overscroll-contain px-5 py-5">
          <AiInfoContent />
        </div>
      </div>
    </div>,
    document.body,
  );
}

type Who = "code" | "ai" | "person";
const WHO: Record<Who, { label: string; cls: string }> = {
  code: { label: "Code on our server", cls: "bg-sunken text-muted" },
  ai: { label: "AI model", cls: "bg-accent/12 text-accent" },
  person: { label: "A person", cls: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]" },
};

const FLOW: { icon: typeof ShieldIcon; title: string; what: string; who: Who[] }[] = [
  { icon: ImageIcon, title: "Read", what: "Text in images, speech in video, artwork and PDFs", who: ["code"] },
  { icon: ReviewIcon, title: "Check", what: "Rules and approved facts first, then tone and claims", who: ["code", "ai"] },
  { icon: SparkIcon, title: "Explain", what: "Why it was flagged, how sure, and a suggested fix", who: ["ai"] },
  { icon: UsersIcon, title: "Decide", what: "Approve, send back, dismiss with a reason", who: ["person"] },
];

const PLACES: { title: string; tone: string; items: string[] }[] = [
  { title: "Stays on our server", tone: "border-line",
    items: ["Reading text in images", "Speech in video", "Matching artwork and faces", "Rule and fact checks",
      "Searching what Inki remembers"] },
  { title: "Sent, redacted", tone: "border-accent/40",
    items: ["Text to gpt-oss for tone, claims and fixes", "Images to gemma, never from confidential pieces",
      "A public post's unsupported claim to web search", "Your Ask Inki messages, to note what to remember"] },
  { title: "Never sent", tone: "border-[var(--vt-blocker)]/40",
    items: ["Confidential codenames", "Confidential pieces to any image model", "Anything internal to web search"] },
];

const GUARDS: { title: string; detail: string }[] = [
  { title: "Every finding cites its source", detail: "The rule, or the approved fact, it was checked against" },
  { title: "AI never approves or publishes", detail: "Only people move a piece forward" },
  { title: "A must-fix needs an approver", detail: "Setting one aside takes a reason, and is recorded" },
  { title: "Every call is on the record", detail: "Decisions go into a tamper-evident audit trail" },
  { title: "Ask Inki sees only what you may open", detail: "Within your clearance, and never confidential pieces" },
  { title: "What Inki remembers is yours", detail: "Only from your own Ask Inki chats, and deletable in Settings. Demo people: per browser, 24 hours" },
];

export function AiInfoContent() {
  return (
    <div className="flex flex-col gap-7 text-sm">
      <section aria-labelledby="ai-flow">
        <h3 id="ai-flow" className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">Who does what</h3>
        <ol className="mt-3 grid gap-2 sm:grid-cols-4">
          {FLOW.map((s, i) => (
            <li key={s.title} className="relative flex gap-3 rounded-xl border border-line bg-surface p-3 sm:flex-col sm:gap-2">
              <span aria-hidden className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${s.who.includes("person")
                ? "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]" : s.who.includes("ai") ? "bg-accent/12 text-accent" : "bg-sunken text-muted"}`}>
                <s.icon size={17} />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold"><span className="text-subtle">{i + 1}.</span> {s.title}</span>
                <span className="mt-0.5 block text-xs leading-5 text-muted">{s.what}</span>
                <span className="mt-1.5 flex flex-wrap gap-1">
                  {s.who.map((w) => (
                    <span key={w} className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${WHO[w].cls}`}>{WHO[w].label}</span>
                  ))}
                </span>
              </span>
              {i < FLOW.length - 1 && (
                <span aria-hidden className="absolute -right-[0.55rem] top-1/2 z-10 hidden h-4 w-4 -translate-y-1/2 place-items-center rounded-full border border-line bg-raised text-[10px] text-subtle sm:grid">
                  &rsaquo;
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="ai-where">
        <h3 id="ai-where" className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">Where your content goes</h3>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {PLACES.map((p) => (
            <div key={p.title} className={`rounded-xl border-2 ${p.tone} bg-surface p-3`}>
              <p className="flex items-center gap-1.5 font-semibold">
                {p.title === "Stays on our server" && <ShieldIcon size={15} className="text-muted" />}
                {p.title}
              </p>
              <ul className="mt-2 flex flex-col gap-1 text-xs leading-5 text-muted">
                {p.items.map((t) => <li key={t} className="flex gap-1.5"><span aria-hidden className="text-subtle">&bull;</span>{t}</li>)}
              </ul>
            </div>
          ))}
        </div>
        {/* What "redacted" means, shown rather than described. */}
        <figure className="mt-3 rounded-xl bg-sunken px-4 py-3">
          <figcaption className="text-[11px] font-medium text-subtle">Before anything leaves, confidential terms are swapped out</figcaption>
          <div className="mt-1.5 flex flex-col gap-1 font-mono text-[12.5px] sm:flex-row sm:items-center sm:gap-3">
            <span>&ldquo;<mark className="rounded bg-[var(--vt-blocker-bg)] px-1 text-[var(--vt-blocker)]">Project Falcon</mark> launches soon&rdquo;</span>
            <span aria-hidden className="text-subtle">&rarr;</span>
            <span className="sr-only">is sent as</span>
            <span>&ldquo;<mark className="rounded bg-accent/12 px-1 text-accent">[[TERM_1]]</mark> launches soon&rdquo;</span>
          </div>
        </figure>
      </section>

      <section aria-labelledby="ai-guards">
        <h3 id="ai-guards" className="text-xs font-semibold uppercase tracking-[0.08em] text-subtle">Guardrails</h3>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {GUARDS.map((g) => (
            <li key={g.title} className="flex gap-2.5 rounded-xl border border-line bg-surface p-3">
              <span aria-hidden className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]">
                <CheckIcon size={12} strokeWidth={3} />
              </span>
              <span><span className="block font-medium">{g.title}</span><span className="block text-xs leading-5 text-muted">{g.detail}</span></span>
            </li>
          ))}
        </ul>
      </section>

      <p className="rounded-xl border border-[var(--vt-warning)]/30 bg-[var(--vt-warning-bg)] px-4 py-3 text-[13px] leading-5">
        <span className="font-semibold text-[var(--vt-warning)]">AI can be wrong, so it never decides alone.</span>{" "}
        <span className="text-muted">Much of a review isn&apos;t AI at all: figures and dates are compared with approved
          facts, and banned words, codenames and artwork are matched against the library, by code. AI reads tone and
          meaning, and explains. Every finding names the rule or fact behind it, and quotes the words when it is about
          words, so you can check it in seconds; a person makes every call. How often each check is right is measured and
          published with the code: the artwork check, for example, catches 96% of misuse and wrongly flags under 5% of
          correct use across 1,200 generated test pictures, though a correctly used wordmark is still flagged about
          one time in seven. Dismissing a finding with a reason teaches Verytas where a rule
          reads unclearly; each review lists the exact models it used, under &ldquo;How it was checked&rdquo;.</span>
      </p>
    </div>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { writeStored, useStored } from "@/lib/stored";
import { useModalFocus } from "./Drawer";
import { useToast } from "./Toaster";
import { useViewer } from "./Viewer";

/** Fired by Settings ("Show the tour again"); the tour starts from its first step. */
export const START_TOUR = "vt-start-tour";

// Each step points at something on every page (a section in the sidebar, the settings button), so the tour
// never has to navigate. A step whose target isn't on screen (the phone layout hides some) is shown centred.
type Step = { target?: string; title: string; body: string };

const MANAGER: Step[] = [
  { title: "Welcome to Verytas",
    body: "Creators send their posts, captions, images, videos and documents here before anything goes out. Verytas checks each one against your brand's rules and approved facts, and your team makes the final call. This tour shows where things are." },
  { target: "/", title: "Dashboard",
    body: "How the work is going: what is waiting for you, what went out, and which rules cause the most back and forth." },
  { target: "/review", title: "Review queue",
    body: "Every piece a creator sends, already checked. Open one to see each issue marked on the post, with the rule or fact behind it. You approve it, ask for changes, or mark an issue as fine. In a video, each issue is a mark on the timeline, and you can drag along it to comment on a stretch; on an image you can draw and write, and the creator sees it in place." },
  { target: "/escalations", title: "Escalations",
    body: "When a creator thinks an issue is wrong, they can ask the brand team to look again. That request is an escalation, and it waits here with both sides of the case." },
  { target: "/conversations", title: "Conversations",
    body: "Talk with a creator beside the piece in question: messages, files, and Meet, Teams or Zoom links that turn into a Join button. Write @Inki to have the assistant answer from the record, once you have agreed it may read the conversation." },
  { target: "/creators", title: "Creators",
    body: "Everyone who writes for the brand, their pieces, and how often their work needs changes." },
  { target: "/library", title: "Brand library",
    body: "What every check uses: your rules, approved facts such as prices and offers, codenames to keep secret, and your official artwork, and the people approved to appear in posts, with the dates their agreements run. The checks are only as good as what is here." },
  { target: "/guidelines", title: "Guideline health",
    body: "Which rules people disagree with or set aside most often, so you can see where a rule needs rewording. Once posts are live, it also shows how posts that ran into a rule did against those that didn't." },
  { target: "/ask", title: "Ask Inki",
    body: "Ask about your workspace in plain words, for example \"what was sent back most this week?\". It sees only what you are allowed to see." },
  { target: "settings", title: "Settings",
    body: "Your profile and the light or dark theme. If you skipped this tour or want it again, it is here under Profile: \"Show the tour again\"." },
];

const CREATOR: Step[] = [
  { title: "Welcome to Verytas",
    body: "Write as you always do. Before a piece reaches the brand team, Verytas checks it against the brand's rules and approved facts, and tells you what to fix and why. This tour shows where things are." },
  { target: "/", title: "My work",
    body: "Your pieces and where each one stands. A \"Draft\" is still being written: the brand team isn't asked to decide on it until you send it." },
  { target: "/review", title: "My reviews",
    body: "Start a piece here: add the caption, images, video or documents, and press \"Run review\". The check takes a few seconds, and each issue comes with the rule behind it. \"Clean\" means nothing must change. Where the brand team marked a moment in your video or drew on your image, you see it right there. Once a piece is approved and posted, add its live link on the piece." },
  { target: "/review", title: "If you disagree",
    body: "Think an issue is wrong? Ask the brand team to look again from the issue itself. That is an escalation: a person decides, and you see the answer here." },
  { target: "/conversations", title: "Conversations",
    body: "Talk with the brand team about a piece without leaving Verytas: messages, files, and meeting links that turn into a Join button. Write @Inki to ask the assistant, once you have agreed it may read the conversation." },
  { target: "/ask", title: "Ask Inki",
    body: "Ask about your own work in plain words, for example \"what do I keep getting wrong?\"." },
  { target: "settings", title: "Settings",
    body: "Your profile and the light or dark theme. If you skipped this tour or want it again, it is here under Profile: \"Show the tour again\"." },
];

const CARD_W = 340;
// Sides whose tour already started by itself in this page load: if the browser blocks storage, "seen" is
// never written, and the tour must not come back on every navigation.
const autoStarted = new Set<string>();
const GAP = 14;

function targetOf(step: Step): HTMLElement | null {
  if (!step.target) return null;
  // The first one on screen: some targets exist twice, once per layout, with one of them hidden.
  return [...document.querySelectorAll<HTMLElement>(`[data-tour="${step.target}"]`)]
    .find((el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }) ?? null;
}

/**
 * The first-visit tour: a spotlight on one part of the console at a time and a card that says what it is
 * for, with Back, Next and Skip. It starts by itself once per side (brand team, creator) in this browser,
 * and Settings starts it again. Plain words throughout, since the people it is for haven't learnt the product's terms yet.
 */
export function Tour() {
  const { me, side, loading } = useViewer();
  const pathname = usePathname();
  const toast = useToast();
  // Once per side per browser, not per account: the demo is one visitor trying several people, and a second
  // brand-team account is the same person who has already had the brand-team tour. Kept in local storage,
  // so it outlives the tab and goes when the site's data is cleared.
  const key = `vt-tour:${side}`;
  const seen = useStored(key);
  const [step, setStep] = useState<number | null>(null);
  const steps = side === "creator" ? CREATOR : MANAGER;

  // The first time this browser lands on this side of the console, not on the sign-in page.
  useEffect(() => {
    if (!me || loading || seen || step !== null || autoStarted.has(key) || pathname.startsWith("/signin")) return;
    const t = setTimeout(() => { autoStarted.add(key); setStep(0); }, 600); // let the page settle first
    return () => clearTimeout(t);
  }, [me, loading, seen, step, key, pathname]);

  useEffect(() => {
    const start = () => setStep(0);
    window.addEventListener(START_TOUR, start);
    return () => window.removeEventListener(START_TOUR, start);
  }, []);

  const end = useCallback((skipped: boolean) => {
    setStep(null);
    writeStored(key, "done");
    if (skipped) toast({ kind: "info", title: "Tour skipped", detail: "Start it again any time from Settings, under Profile." });
  }, [key, toast]);

  if (step === null || !me) return null;
  return <TourStep steps={steps} index={Math.min(step, steps.length - 1)} onGo={setStep} onEnd={end} />;
}

function TourStep({ steps, index, onGo, onEnd }: {
  steps: Step[]; index: number; onGo: (i: number) => void; onEnd: (skipped: boolean) => void;
}) {
  const step = steps[index];
  const last = index === steps.length - 1;
  const card = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [size, setSize] = useState({ w: CARD_W, h: 200 });

  // Follow the target as the page scrolls or resizes; the phone's tab bar scrolls sideways to show it.
  useLayoutEffect(() => {
    const el = targetOf(step);
    el?.scrollIntoView({ block: "nearest", inline: "center" });
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setRect(targetOf(step)?.getBoundingClientRect() ?? null));
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure, true); };
  }, [step]);

  // A modal like any other: focus stays in the card, the page behind is inert, Escape skips.
  useModalFocus(card, () => onEnd(true));

  useLayoutEffect(() => {
    const el = card.current;
    // scrollHeight: the card's full height even while a short screen caps it.
    if (el) setSize({ w: el.offsetWidth, h: el.scrollHeight + 2 });
  }, [index, rect]);

  // Each step is announced from its start; not on scroll or resize, which would pull focus off a button.
  useLayoutEffect(() => { card.current?.focus(); }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Plain arrows only: Alt or Cmd with an arrow is the browser's Back, and a held key would race through.
      if (e.repeat || e.altKey || e.metaKey || e.ctrlKey || e.shiftKey) return;
      if (e.key === "ArrowRight") { if (last) onEnd(false); else onGo(index + 1); }
      else if (e.key === "ArrowLeft" && index > 0) onGo(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, last, onGo, onEnd]);

  const vw = typeof window === "undefined" ? 1280 : window.innerWidth;
  const vh = typeof window === "undefined" ? 800 : window.innerHeight;
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, Math.max(lo, hi)));
  let maxHeight: number | undefined;
  let left = (vw - size.w) / 2;
  let top = (vh - size.h) / 2;
  if (rect) {
    if (rect.right + GAP + size.w <= vw - 16) {
      left = rect.right + GAP;
      top = clamp(rect.top + rect.height / 2 - size.h / 2, 16, vh - size.h - 16);
    } else {
      left = clamp(rect.left + rect.width / 2 - size.w / 2, 16, vw - size.w - 16);
      const below = vh - 16 - (rect.bottom + GAP);
      const above = rect.top - GAP - 16;
      if (size.h <= below) top = rect.bottom + GAP;
      else if (size.h <= above) top = rect.top - GAP - size.h;
      else {
        // A short landscape phone: neither side has room, so the card takes the larger one and scrolls
        // inside, rather than covering what it points at.
        top = below >= above ? rect.bottom + GAP : 16;
        maxHeight = Math.max(below, above);
      }
    }
  }

  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-[60]">
      {/* Holds clicks for the length of the tour, so a stray one doesn't navigate away under it. */}
      <div className="absolute inset-0" aria-hidden />
      {rect ? (
        <div aria-hidden className="vt-tour-spot pointer-events-none fixed rounded-xl"
          style={{ left: rect.left - 6, top: rect.top - 6, width: rect.width + 12, height: rect.height + 12 }} />
      ) : (
        <div aria-hidden className="vt-tour-dim pointer-events-none absolute inset-0" />
      )}
      <div ref={card} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}
        className="vt-tour-card fixed flex max-h-[calc(100dvh-2rem)] flex-col gap-3 overflow-y-auto rounded-2xl border border-line bg-raised p-5 shadow-[var(--vt-shadow-pop)] outline-none"
        style={{ left, top, maxHeight, width: `min(${CARD_W}px, calc(100vw - 32px))` }}>
        <p className="text-xs font-medium text-subtle" aria-live="polite">Step {index + 1} of {steps.length}</p>
        <h2 id={titleId} className="text-base font-semibold leading-snug">{step.title}</h2>
        <p className="text-sm leading-6 text-muted">{step.body}</p>
        <div className="mt-1 flex items-center gap-2">
          <button type="button" onClick={() => onEnd(true)} className="vt-btn h-9 mr-auto rounded-full px-4">
            Skip
          </button>
          {index > 0 && (
            <button type="button" onClick={() => onGo(index - 1)} className="vt-btn vt-btn-quiet h-9 rounded-full px-4">Back</button>
          )}
          <button type="button" onClick={() => (last ? onEnd(false) : onGo(index + 1))}
            className="vt-btn vt-btn-primary h-9 rounded-full px-4 font-semibold">
            {last ? "Done" : "Next"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

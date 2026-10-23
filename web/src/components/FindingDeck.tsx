"use client";

import { type ReactNode, useState } from "react";
import { AlertIcon, InfoIcon, OctagonIcon } from "./Icons";

type Card = {
  level: string; Icon: typeof AlertIcon; tone: string; bg: string; kind: string;
  before: string; mark: string; after: string; chips: string[]; fix: ReactNode;
};

// Example findings, one of each kind, laid out the way the product shows a finding.
const CARDS: Card[] = [
  { level: "Blocker", Icon: OctagonIcon, tone: "text-[var(--vt-blocker)]", bg: "bg-[var(--vt-blocker-bg)]", kind: "Claim contradicts an approved fact",
    before: "“Learn with India's favourite app: Kitepath has ", mark: "2 million learners", after: ".”",
    chips: ["Approved fact: 1.2 million learners", "Annual report 2026, p.4"],
    fix: <>Kitepath has <strong className="font-semibold">1.2 million learners</strong></> },
  { level: "Advisory", Icon: InfoIcon, tone: "text-accent", bg: "bg-accent/12", kind: "Hashtag hard to read aloud",
    before: "“Start today ", mark: "#learnwithkitepath", after: "”", chips: ["Rule: CamelCase hashtags", "WCAG 2.2"],
    fix: <>Start today <strong className="font-semibold">#LearnWithKitepath</strong></> },
  { level: "Blocker", Icon: OctagonIcon, tone: "text-[var(--vt-blocker)]", bg: "bg-[var(--vt-blocker-bg)]", kind: "Official artwork distorted",
    before: "Kitepath logo on the poster, ", mark: "stretched to 130% of its width", after: ".", chips: ["Rule: keep its proportions", "Logo kit 2026"],
    fix: <>Use the logo at <strong className="font-semibold">its own proportions</strong></> },
  { level: "Warning", Icon: AlertIcon, tone: "text-[var(--vt-warning)]", bg: "bg-[var(--vt-warning-bg)]", kind: "Pressure in the tone",
    before: "“", mark: "Hurry!!! Only 2 seats left", after: ". Join today.”", chips: ["Rule: no countdown pressure", "Brand book, p.7"],
    fix: <>Seats are <strong className="font-semibold">limited this month</strong>. Join today.</> },
];

/**
 * The example findings as a deck. Pointing at it fans out the cards behind; a click (or Enter) sends the
 * top card to the back and brings the next one forward, round and round. Nothing on screen says so, on
 * purpose: it is there to be found.
 * Each card's place in the deck is a slot (0 is the top); styles in globals.css move them between slots.
 * The cards share one grid cell, so every card is as tall as the tallest and the deck stays square.
 */
export function FindingDeck() {
  const [top, setTop] = useState(0);
  const [leaving, setLeaving] = useState(false);

  function next() {
    if (leaving) return;
    // The top card first drops out below, still in front, then takes the back slot and slides behind.
    setLeaving(true);
    window.setTimeout(() => { setTop((t) => (t + 1) % CARDS.length); setLeaving(false); }, 260);
  }

  const current = CARDS[top];
  return (
    <div className="my-auto hidden max-w-md sm:block">
      <button type="button" onClick={next} aria-label={`Example finding: ${current.level}, ${current.kind}. Show the next example.`}
        className="vt-deck grid w-full cursor-default text-left">
        {CARDS.map((c, i) => {
          const slot = (i - top + CARDS.length) % CARDS.length;
          return (
            <div key={c.kind} aria-hidden
              className={`vt-deck-card vt-slot-${slot} ${slot === 0 && leaving ? "vt-deck-leaving" : ""} [grid-area:1/1] flex flex-col gap-3 rounded-2xl border border-line bg-raised p-4 shadow-[var(--vt-shadow-pop)]`}>
              <div className={`flex items-center gap-2 text-xs font-semibold ${c.tone}`}>
                <c.Icon size={14} />{c.level}<span className="font-normal text-subtle">· {c.kind}</span>
              </div>
              <p className="text-sm leading-6">{c.before}<mark className={`rounded px-0.5 ${c.bg} ${c.tone}`}>{c.mark}</mark>{c.after}</p>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {c.chips.map((t) => <span key={t} className="rounded-full border border-line bg-surface px-2.5 py-1 text-muted">{t}</span>)}
              </div>
              <div className="mt-auto flex items-center justify-between gap-3 rounded-xl bg-sunken px-3 py-2 text-sm">
                <span className="min-w-0 truncate">{c.fix}</span>
                <span className="shrink-0 rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-accent-ink">Accept fix</span>
              </div>
            </div>
          );
        })}
      </button>
    </div>
  );
}

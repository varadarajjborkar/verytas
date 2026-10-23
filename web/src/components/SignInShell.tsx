import type { ReactNode } from "react";
import { CheckIcon, OctagonIcon } from "./Icons";
import { Wordmark } from "./Wordmark";

// The cards behind the example: other kinds of finding, one line each.
const DECK = [
  { level: "Warning", kind: "Tone", tone: "text-[var(--vt-warning)]", text: "“Hurry!!! Only 2 seats left” reads as pressure. Try “Seats are limited this month.”" },
  { level: "Blocker", kind: "Visual", tone: "text-[var(--vt-blocker)]", text: "The logo is stretched to 130% of its width. Use it at its own proportions." },
  { level: "Advisory", kind: "Accessibility", tone: "text-accent", text: "#learnwithkitepath is hard to read aloud. Try #LearnWithKitepath." },
];

const PROMISES = [
  "Claims are checked against facts the brand approved",
  "Every flag says why and cites its source",
  "People make the final call, and it is recorded",
];

/**
 * The front door, for the demo picker and the token form alike: what Verytas is on the left (a real
 * finding, the way the product shows one), the way in on the right. Stacks on a phone, brand first but
 * short, so the choice is still on the first screen.
 */
export function SignInShell({ children }: { children: ReactNode }) {
  return (
    <div className="vt-card mx-auto grid w-full max-w-6xl overflow-hidden md:min-h-[calc(100vh-4.5rem)] md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <aside className="vt-signin-aside relative flex flex-col gap-8 border-b border-line p-6 md:border-b-0 md:border-r md:p-10">
        <Wordmark size="lg" />
        <div className="flex flex-col gap-3">
          <h2 className="text-[1.65rem] font-semibold leading-tight tracking-tight md:text-[2rem]">
            Brand review that shows its work.
          </h2>
          <p className="max-w-md text-sm leading-6 text-muted">
            Every post, caption and piece of artwork is checked before it goes out, and every flag comes with
            the rule or fact behind it.
          </p>
        </div>

        {/* A deck: on hover, the findings behind the top one fan out at a tilt, far enough to read their
            first line and no further, then settle back when the pointer leaves. */}
        <div className="vt-deck relative my-auto hidden max-w-md sm:block">
          {DECK.map((c, i) => (
            <div key={c.kind} aria-hidden className={`vt-deck-card vt-deck-${i} absolute inset-x-3 top-1/2 flex flex-col gap-1.5 rounded-2xl border border-line bg-raised px-4 py-3 shadow-[var(--vt-shadow-pop)] ${i === 1 ? "justify-end" : ""}`}>
              <div className={`flex items-center gap-2 text-xs font-semibold ${c.tone}`}>
                <span className="h-2 w-2 shrink-0 rounded-full bg-current" />{c.level}
                <span className="truncate font-normal text-subtle">· {c.kind}</span>
              </div>
              <p className="truncate text-xs leading-5 text-muted">{c.text}</p>
            </div>
          ))}
        <figure aria-label="An example finding" className="vt-signin-sample relative z-10 flex flex-col gap-3 rounded-2xl border border-line bg-raised p-4 shadow-[var(--vt-shadow-pop)]">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--vt-blocker)]">
            <OctagonIcon size={14} />Blocker
            <span className="font-normal text-subtle">· Claim contradicts an approved fact</span>
          </div>
          <p className="text-sm leading-6">
            “Learn with India&apos;s favourite app: Kitepath has <mark className="rounded bg-[var(--vt-blocker-bg)] px-0.5 text-[var(--vt-blocker)]">2 million learners</mark>.”
          </p>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full border border-line bg-surface px-2.5 py-1 text-muted">Approved fact: 1.2 million learners</span>
            <span className="rounded-full border border-line bg-surface px-2.5 py-1 text-muted">Annual report 2026, p.4</span>
          </div>
          <div className="flex items-center justify-between gap-3 rounded-xl bg-sunken px-3 py-2 text-sm">
            <span className="min-w-0 truncate">Kitepath has <strong className="font-semibold">1.2 million learners</strong></span>
            <span className="shrink-0 rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-accent-ink">Accept fix</span>
          </div>
        </figure>
        </div>

        <ul className="hidden flex-col gap-2.5 text-sm sm:flex">
          {PROMISES.map((p) => (
            <li key={p} className="flex items-start gap-2.5">
              <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent/12 text-accent"><CheckIcon size={12} /></span>
              <span className="text-muted">{p}</span>
            </li>
          ))}
        </ul>
      </aside>
      <section className="flex flex-col gap-7 bg-surface p-6 md:p-10">{children}</section>
    </div>
  );
}

// The way a piece travels from first draft to published, drawn twice: as a
// row of dots in lists, and as a full map at the top of an open review.

import { relativeTime } from "@/lib/review-client";
import { type Journey, STAGES, stageOf } from "@/lib/journey";
import type { ContentStatus } from "@/lib/types";
import { CheckIcon, RefreshIcon } from "./Icons";

/** Five dots, filled up to the stage reached; a loop mark when the piece was sent back. */
export function StageDots({ status, checked }: { status: ContentStatus; checked: boolean }) {
  const at = stageOf(status, checked);
  const label = at < 0 ? "Withdrawn" : `${STAGES[at]}, step ${at + 1} of ${STAGES.length}`;
  return (
    <span role="img" aria-label={label} title={label} className="inline-flex items-center gap-1">
      {STAGES.map((s, i) => (
        <span key={s} className={`h-1.5 w-1.5 rounded-full ${
          at < 0 ? "bg-line-strong" : i < at ? "bg-accent" : i === at ? "bg-accent ring-2 ring-accent/25" : "bg-line-strong"}`} />
      ))}
      {status === "changes_requested" && <RefreshIcon size={11} className="ml-0.5 text-[var(--vt-warning)]" />}
    </span>
  );
}

/** The whole route with what happened at each stop: when, by whom and how it went. */
export function JourneyMap({ journey, status }: { journey: Journey; status: ContentStatus }) {
  const { milestones, rounds, lastSentBack, withdrawn } = journey;
  return (
    <section aria-label="Where this piece is" className="vt-card px-4 py-4 md:px-5">
      <ol className="flex flex-col gap-3 md:flex-row md:items-start md:gap-0">
        {milestones.map((m, i) => {
          // The loop sits on the road between "Checked" and "Sent for approval": sent back, fixed, re-checked.
          const loopHere = i === 1 && rounds > 0;
          return (
            <li key={m.label} className="relative flex gap-3 md:flex-1 md:flex-col md:gap-2">
              {/* The road to the next stop: down the side on phones, across on wider screens. */}
              {i < milestones.length - 1 && (
                <span aria-hidden className={`absolute -bottom-2.5 left-[11px] top-7 w-px md:bottom-auto md:left-8 md:right-2 md:top-[11px] md:h-px md:w-auto ${
                  milestones[i + 1].state === "todo" ? "bg-line-strong" : "bg-accent"}`} />
              )}
              <span className={`relative z-[1] grid h-6 w-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold ${
                m.state === "done" ? "border-accent bg-accent text-accent-ink"
                  : m.state === "current" ? "border-accent bg-raised text-accent ring-4 ring-accent/15"
                    : "border-line-strong bg-raised text-subtle"}`}>
                {m.state === "done" ? <CheckIcon size={13} strokeWidth={2.5} /> : i + 1}
              </span>
              <div className="min-w-0 md:pr-3">
                <p className={`text-[13px] font-medium ${m.state === "todo" ? "text-subtle" : ""}`}>
                  {m.label}
                  {m.state === "current" && <span className="sr-only"> (current step)</span>}
                </p>
                {m.at && (
                  <p className="truncate text-[11px] text-subtle" title={new Date(m.at).toLocaleString()}>
                    {relativeTime(m.at)}{m.who ? ` · ${m.who.name}` : ""}
                  </p>
                )}
                {m.detail && <p className="mt-0.5 line-clamp-2 text-[11px] text-muted">{m.detail}</p>}
                {loopHere && (
                  <p className="mt-1.5 inline-flex items-center gap-1 rounded-md bg-[var(--vt-warning-bg)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--vt-warning)]">
                    <RefreshIcon size={11} /> Sent back {rounds === 1 ? "once" : `${rounds} times`}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {(status === "changes_requested" && lastSentBack) || withdrawn ? (
        <p className="mt-3.5 border-t border-line pt-3 text-xs text-muted">
          {withdrawn ? "Withdrawn. Nothing more happens to this piece."
            : <>
                <span className="font-medium text-ink">Changes requested</span>
                {lastSentBack?.who ? ` by ${lastSentBack.who.name}` : ""}
                {lastSentBack?.note ? <>: &ldquo;{lastSentBack.note}&rdquo;</> : ". Fix the issues, re-check, then send it again."}
              </>}
        </p>
      ) : null}
    </section>
  );
}

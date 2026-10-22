// The way a piece travels from first draft to published, drawn twice: as a
// row of dots in lists, and as a full map at the top of an open review.

import { relativeTime } from "@/lib/review-client";
import { type Journey, STAGES, stageOf } from "@/lib/journey";
import type { ContentStatus } from "@/lib/types";
import { CheckIcon, RefreshIcon } from "./Icons";

/**
 * The route in miniature: five stops on one line, travelled up to the stage reached.
 * The same drawing as the journey map, so a row in any list reads like the map it opens.
 */
export function StageDots({ status, checked }: { status: ContentStatus; checked: boolean }) {
  const at = stageOf(status, checked);
  const label = at < 0 ? "Withdrawn" : `${STAGES[at]}, step ${at + 1} of ${STAGES.length}`;
  const x = (i: number) => 4 + i * 14;
  return (
    <span role="img" aria-label={label} title={label} className="inline-flex items-center gap-1">
      <svg width="64" height="10" viewBox="0 0 64 10" aria-hidden className="shrink-0 overflow-visible">
        <line x1={x(0)} x2={x(4)} y1="5" y2="5" stroke="var(--vt-line-strong)" strokeWidth="1.5" strokeLinecap="round" />
        {at > 0 && <line x1={x(0)} x2={x(at)} y1="5" y2="5" stroke="var(--vt-accent)" strokeWidth="1.5" strokeLinecap="round" />}
        {STAGES.map((s, i) => (
          <circle key={s} cx={x(i)} cy="5" r={i === at ? 3.25 : 2.25}
            fill={at >= 0 && i <= at ? "var(--vt-accent)" : "var(--vt-raised)"}
            stroke={at >= 0 && i <= at ? "var(--vt-accent)" : "var(--vt-line-strong)"} strokeWidth="1.25" />
        ))}
        {at >= 0 && <circle cx={x(at)} cy="5" r="5.5" fill="none" stroke="var(--vt-accent)" strokeOpacity="0.25" strokeWidth="2" />}
      </svg>
      {status === "changes_requested" && <RefreshIcon size={11} className="text-[var(--vt-warning)]" />}
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
                  <span className="sr-only">{m.state === "current" ? " (current step)" : m.state === "done" ? " (done)" : " (not yet)"}</span>
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

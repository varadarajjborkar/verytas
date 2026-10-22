import Link from "next/link";
import { ArrowRightIcon, RefreshIcon } from "../Icons";

// Fixed per stage, so a stage keeps its colour whichever others are empty.
const STAGES = [
  { key: "draft", label: "Draft", hint: "Being written", colour: "#8a93a3", queue: "creator" },
  { key: "in_review", label: "In review", hint: "Waiting for you", colour: "#3d8bf2", queue: "waiting" },
  { key: "approved", label: "Approved", hint: "Ready to go out", colour: "#4fb487", queue: "approved" },
  { key: "published", label: "Published", hint: "Live", colour: "#22b8a6", queue: "approved" },
] as const;

/** The approval pipeline as a flow: each stage with its count, and the loop back to creators. */
export function PipelineFlow({ counts }: { counts: Record<string, number> }) {
  const back = counts.changes_requested ?? 0;
  return (
    <div>
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-0">
        {STAGES.map((s, i) => (
          <li key={s.key} className="relative flex items-center sm:pr-6">
            <Link href={`/review?queue=${s.queue}`}
              className="vt-lift flex w-full flex-col rounded-xl border border-line bg-raised px-3 py-2.5 hover:border-line-strong">
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted">
                <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: s.colour }} />{s.label}
              </span>
              <span className="mt-1 text-2xl font-semibold leading-none tabular-nums">{counts[s.key] ?? 0}</span>
              <span className="mt-1 truncate text-[11px] text-subtle">{s.hint}</span>
            </Link>
            {i < STAGES.length - 1 && (
              <ArrowRightIcon aria-hidden size={14} className="absolute right-1 top-1/2 hidden -translate-y-1/2 text-subtle sm:block" />
            )}
          </li>
        ))}
      </ol>
      {/* The return lane: in review, sent back, fixed by the creator and sent again. */}
      <div className="relative mt-1 hidden h-6 sm:block" aria-hidden>
        <svg className="absolute inset-y-0 left-[12.5%] w-[25%] overflow-visible text-[var(--vt-warning)]" viewBox="0 0 100 24"
          preserveAspectRatio="none">
          <path d="M100 0 V16 H0 V2" fill="none" stroke="currentColor" strokeWidth="1.25" strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <Link href="/review?queue=creator"
        className="mt-2 flex items-center gap-2 rounded-lg border border-dashed border-[var(--vt-warning)]/50 bg-[var(--vt-warning-bg)] px-3 py-2 text-xs text-[var(--vt-warning)] sm:mx-[6%] sm:w-[38%]">
        <RefreshIcon size={13} className="shrink-0" />
        <span><span className="font-semibold tabular-nums">{back}</span> sent back for changes</span>
      </Link>
    </div>
  );
}

// Small presentational helpers shared across pages.

import type { ReactNode } from "react";
import type { Level, Source } from "@/lib/types";
import { AlertIcon, ChevronIcon, InfoIcon, OctagonIcon } from "./Icons";
import { RefreshButton } from "./RefreshButton";

export const HEADER_BACK = "vt-header-back";

export function PageHeader({ title, lead, aside, refresh = false }: { title: string; lead?: string; aside?: ReactNode; refresh?: boolean }) {
  return (
    <div className="mb-7 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        {/* A detail view puts its way back just before the title (BackButton): a chevron that hangs in the
            margin on wider screens, so every title still starts where the others do. */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          {/* 2rem button + 0.375rem gap, pulled back by the same 2.375rem: inside the main column's 2.5rem margin. */}
          <span id={HEADER_BACK} className="-mr-2.5 flex empty:hidden md:-ml-[2.375rem]" />
          <h1 className="text-[1.65rem] font-semibold leading-tight tracking-tight">{title}</h1>
          {/* On a phone the refresh rides in the title row as an icon, not a row of its own under the lead. */}
          {refresh && <span className="ml-auto md:hidden"><RefreshButton compact /></span>}
        </div>
        {lead && <p className="mt-1.5 max-w-xl text-sm text-muted">{lead}</p>}
      </div>
      {(aside || refresh) && <div className={`flex-wrap items-center gap-2 ${aside ? "flex" : "hidden md:flex"}`}>{aside}{refresh && <span className="hidden md:inline-flex"><RefreshButton /></span>}</div>}
    </div>
  );
}

/** Says so only when a page is showing sample data; live data is the normal case and needs no badge. */
export function SourceBadge({ source }: { source: Source }) {
  const live = source === "live";
  if (live) return null;
  return (
    <span title={live ? undefined : "The backend isn't connected, so this shows sample data."}
      className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-muted">
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${live ? "bg-[var(--vt-ok)]" : "bg-[var(--vt-warning)]"}`} />
      {live ? "Live" : "Sample data"}
    </span>
  );
}

const LEVEL_META: Record<Level, { label: string; Icon: typeof InfoIcon; cls: string }> = {
  blocker: { label: "Blocker", Icon: OctagonIcon, cls: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)]" },
  warning: { label: "Warning", Icon: AlertIcon, cls: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]" },
  advisory: { label: "Advisory", Icon: InfoIcon, cls: "bg-[var(--vt-advisory-bg)] text-[var(--vt-advisory)]" },
};

export function LevelPill({ level }: { level: Level }) {
  const { label, Icon, cls } = LEVEL_META[level];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold ${cls}`}>
      <Icon size={12} strokeWidth={2.25} />
      {label}
    </span>
  );
}

/** A rule's code, set wide enough for the longest built-in ones (CLAIM-CONTRADICTED). */
export function RuleCode({ code, className = "" }: { code: string; className?: string }) {
  return <code title={code} className={`shrink-0 truncate font-mono text-[11px] text-muted ${className}`}>{code}</code>;
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="vt-card vt-lift p-4">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className="mt-1.5 text-[1.6rem] font-semibold leading-none tracking-tight tabular-nums">{value}</p>
      {hint && <p className="mt-2 line-clamp-2 text-xs leading-5 text-subtle" title={hint}>{hint}</p>}
    </div>
  );
}

export function Panel({ title, aside, children, className = "", scroll = false }: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  /** A list that can grow: it scrolls inside the panel past a set height, so one long list never
   *  stretches its box out of line with the panels beside it. */
  scroll?: boolean;
}) {
  return (
    // min-w-0: as a grid or flex item a panel would otherwise grow to its widest
    // child (charts draw at a fixed width) and push the page sideways on phones.
    <section className={`vt-card min-w-0 p-4 md:p-5 ${className}`} aria-label={title}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {aside}
      </div>
      <div className={scroll ? "vt-scroll -mr-2 mt-4 max-h-[22rem] overflow-y-auto overscroll-contain pr-2" : "mt-4"}
        tabIndex={scroll ? 0 : undefined}>{children}</div>
    </section>
  );
}

/** Secondary detail, closed until asked for, so the page leads with what matters. */
export function Details({ summary, children, className = "" }: { summary: ReactNode; children: ReactNode; className?: string }) {
  return (
    <details className={`group vt-card min-w-0 ${className}`}>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3.5 text-sm font-medium md:px-5 [&::-webkit-details-marker]:hidden">
        {summary}
        <ChevronIcon size={16} className="shrink-0 text-muted transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="border-t border-line px-4 py-4 md:px-5">{children}</div>
    </details>
  );
}

export function Meter({ value, label, tone = "accent" }: { value: number; label: string; tone?: "accent" | "danger" | "ok" }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const colour = tone === "danger" ? "var(--vt-blocker)" : tone === "ok" ? "var(--vt-ok)" : "var(--vt-accent)";
  return (
    <div className="flex items-center gap-2.5">
      <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}
        className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
        <div className="h-full rounded-full transition-[width] duration-500 ease-out" style={{ width: `${pct}%`, background: colour }} />
      </div>
      <span className="w-9 text-right text-xs tabular-nums text-muted">{pct}%</span>
    </div>
  );
}

export { TrendBars } from "./TrendBars";

/** Labelled horizontal bars, sized to the card, no internal scrolling. */
export function HBars({ data, colour = "var(--vt-accent)" }: { data: { label: string; value: number }[]; colour?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <ul className="flex flex-col gap-3.5">
      {data.map((d) => (
        <li key={d.label}>
          <div className="mb-1.5 flex justify-between text-xs">
            <span className="capitalize">{d.label}</span>
            <span className="tabular-nums text-muted">{d.value}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-sunken">
            <div className="vt-grow-x h-full rounded-full" style={{ width: `${(d.value / max) * 100}%`, background: colour }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Placeholder blocks shaped like the page, shown while server data loads. */
export function PageSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading" className="flex animate-pulse flex-col gap-5">
      <div className="h-8 w-56 rounded-lg bg-sunken" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-[5.5rem] rounded-[14px] bg-sunken" />)}
      </div>
      <div className="h-72 rounded-[14px] bg-sunken" />
    </div>
  );
}

/**
 * Arrow keys for a tablist, as WAI-ARIA expects: move the choice and the focus together.
 * Each tab needs the id `${idPrefix}-${value}`.
 */
export function tabKeys<T extends string>(values: readonly T[], current: T, pick: (v: T) => void, idPrefix: string) {
  return (e: { key: string; preventDefault: () => void }) => {
    const step = ({ ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 } as Record<string, number>)[e.key];
    if (!step) return;
    e.preventDefault();
    const next = values[(values.indexOf(current) + step + values.length) % values.length];
    pick(next);
    requestAnimationFrame(() => document.getElementById(`${idPrefix}-${next}`)?.focus());
  };
}

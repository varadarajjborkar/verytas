// Small presentational helpers shared across pages.

import type { ReactNode } from "react";
import type { Level, Source } from "@/lib/types";
import { AlertIcon, ChevronIcon, InfoIcon, OctagonIcon } from "./Icons";

export function PageHeader({ title, lead, aside }: { title: string; lead?: string; aside?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-[1.65rem] font-semibold leading-tight tracking-tight">{title}</h1>
        {lead && <p className="mt-1.5 max-w-xl text-sm text-muted">{lead}</p>}
      </div>
      {aside}
    </div>
  );
}

export function SourceBadge({ source }: { source: Source }) {
  const live = source === "live";
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
      {hint && <p className="mt-2 truncate text-xs text-subtle" title={hint}>{hint}</p>}
    </div>
  );
}

export function Panel({ title, aside, children, className = "" }: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    // min-w-0: as a grid or flex item a panel would otherwise grow to its widest
    // child (charts draw at a fixed width) and push the page sideways on phones.
    <section className={`vt-card min-w-0 p-4 md:p-5 ${className}`} aria-label={title}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {aside}
      </div>
      <div className="mt-4">{children}</div>
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

/**
 * Stacked daily bars that always fit their card. The charting library pages its
 * x-axis by width, which hid the most recent days on narrow screens. Bars are capped
 * in width so a short range doesn't turn into slabs, segments are split by a 2px gap,
 * and the whole column is the hover target, with the day's breakdown in a tooltip.
 */
export function TrendBars({ data, series }: {
  data: { label: string; values: number[] }[];
  series: { name: string; colour: string }[];
}) {
  const totals = data.map((d) => d.values.reduce((a, b) => a + b, 0));
  const max = Math.max(1, ...totals);
  // One reference line at a round number near the top (9, 20, 300) gives the bars a scale without a grid.
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const ref = Math.floor(max / magnitude) * magnitude;
  return (
    <div className="flex h-full flex-col">
      <div className="relative min-h-0 flex-1" role="img"
        aria-label={`Daily findings: ${data.map((d, i) => `${d.label} ${totals[i]}`).join(", ")}`}>
        <div aria-hidden className="absolute inset-x-0 border-t border-dashed border-line" style={{ bottom: `${(ref / max) * 92}%` }}>
          <span className="absolute -top-2.5 left-0 bg-surface pr-1.5 text-[11px] tabular-nums text-subtle">{ref}</span>
        </div>
        <div className="absolute inset-0 flex items-end gap-1.5 border-b border-line-strong">
          {data.map((d, i) => (
            <div key={d.label} className="group relative flex h-full min-w-0 flex-1 justify-center">
              <div className="vt-grow flex h-full w-full max-w-7 flex-col justify-end" style={{ "--vt-i": i } as React.CSSProperties}>
                <div className="flex w-full flex-col-reverse gap-[2px] transition-opacity group-hover:opacity-100 [@media(hover:hover)]:opacity-85"
                  style={{ height: `${(totals[i] / max) * 92}%` }}>
                  {d.values.map((v, k) => v > 0 && (
                    <div key={k} className="rounded-[2px] last:rounded-t-[4px]" style={{ flexGrow: v, background: series[k].colour }} />
                  ))}
                </div>
              </div>
              {totals[i] > 0 && (
                <div aria-hidden className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 whitespace-nowrap rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs shadow-[var(--vt-shadow-pop)] group-hover:block">
                  <p className="font-semibold">{d.label} · {totals[i]}</p>
                  {d.values.map((v, k) => v > 0 && (
                    <p key={k} className="flex items-center gap-1.5 text-muted">
                      <span className="h-2 w-2 rounded-full" style={{ background: series[k].colour }} />{series[k].name} {v}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-1.5 flex gap-1.5">
        {data.map((d, i) => (
          <span key={d.label} className="min-w-0 flex-1 truncate text-center text-[11px] tabular-nums text-subtle">
            {/* Every other day, counted back from today so the latest is always labelled. */}
            {(data.length - 1 - i) % 2 === 0 ? d.label : ""}
          </span>
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {series.map((s) => (
          <li key={s.name} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: s.colour }} />{s.name}
          </li>
        ))}
      </ul>
    </div>
  );
}

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

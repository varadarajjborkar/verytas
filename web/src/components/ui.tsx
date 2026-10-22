// Small presentational helpers shared across pages.

import type { ReactNode } from "react";
import type { Level, Source } from "@/lib/types";

export function PageHeader({ title, lead, aside }: { title: string; lead: string; aside?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">{lead}</p>
      </div>
      {aside}
    </div>
  );
}

export function SourceBadge({ source }: { source: Source }) {
  if (source === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--vt-ok-bg)] px-3 py-1 text-xs font-medium text-[var(--vt-ok)]">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[var(--vt-ok)]" /> Live data
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-[var(--vt-warning-bg)] px-3 py-1 text-xs font-medium text-[var(--vt-warning)]"
      title="The backend is not configured or not reachable, so this page shows sample data."
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[var(--vt-warning)]" /> Demo data
    </span>
  );
}

const LEVEL_META: Record<Level, { label: string; icon: string; cls: string }> = {
  blocker: { label: "Blocker", icon: "⛔", cls: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)]" },
  warning: { label: "Warning", icon: "⚠", cls: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]" },
  advisory: { label: "Advisory", icon: "ℹ", cls: "bg-[var(--vt-advisory-bg)] text-[var(--vt-advisory)]" },
};

export function LevelPill({ level }: { level: Level }) {
  const m = LEVEL_META[level];
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold ${m.cls}`}>
      <span aria-hidden>{m.icon}</span>
      {m.label}
    </span>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Panel({ title, subtitle, children, className = "" }: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    // min-w-0: as a grid or flex item a panel would otherwise grow to its widest
    // child (charts draw at a fixed width) and push the page sideways on phones.
    <section className={`min-w-0 rounded-xl border border-line bg-surface p-4 md:p-5 ${className}`} aria-label={title}>
      <h2 className="text-sm font-semibold">{title}</h2>
      {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function Meter({ value, label, tone = "accent" }: { value: number; label: string; tone?: "accent" | "danger" | "ok" }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const colour = tone === "danger" ? "var(--vt-blocker)" : tone === "ok" ? "var(--vt-ok)" : "var(--vt-accent)";
  return (
    <div className="flex items-center gap-2">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="h-2 w-full overflow-hidden rounded-full bg-line"
      >
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: colour }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-muted">{pct}%</span>
    </div>
  );
}

/**
 * Stacked daily bars that always fit their card. The charting library pages its
 * x-axis by width, which hid the most recent days on narrow screens.
 */
export function TrendBars({ data, series }: {
  data: { label: string; values: number[] }[];
  series: { name: string; colour: string }[];
}) {
  const max = Math.max(1, ...data.map((d) => d.values.reduce((a, b) => a + b, 0)));
  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1 items-end gap-1.5 border-b border-line pb-px" role="img"
        aria-label={`Daily findings: ${data.map((d) => `${d.label} ${d.values.reduce((a, b) => a + b, 0)}`).join(", ")}`}>
        {data.map((d) => {
          const total = d.values.reduce((a, b) => a + b, 0);
          return (
            <div key={d.label} className="group relative flex h-full min-w-0 flex-1 flex-col justify-end" title={`${d.label}: ${total}`}>
              {total > 0 && (
                <span className="mb-1 text-center text-[10px] tabular-nums text-muted">{total}</span>
              )}
              <div className="flex w-full flex-col-reverse overflow-hidden rounded-t" style={{ height: `${(total / max) * 85}%` }}>
                {d.values.map((v, i) => v > 0 && (
                  <div key={i} style={{ height: `${(v / total) * 100}%`, background: series[i].colour }} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex gap-1.5">
        {data.map((d) => <span key={d.label} className="min-w-0 flex-1 truncate text-center text-[10px] text-muted">{d.label}</span>)}
      </div>
      <ul className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs">
        {series.map((s) => (
          <li key={s.name} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: s.colour }} />{s.name}
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
    <ul className="flex flex-col gap-3">
      {data.map((d) => (
        <li key={d.label}>
          <div className="mb-1 flex justify-between text-xs">
            <span className="capitalize">{d.label}</span>
            <span className="tabular-nums text-muted">{d.value}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full" style={{ width: `${(d.value / max) * 100}%`, background: colour }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

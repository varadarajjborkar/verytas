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
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#dcfae6] px-3 py-1 text-xs font-medium text-[#067647]">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#067647]" /> Live data
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-[#fef0c7] px-3 py-1 text-xs font-medium text-[#93370d]"
      title="The backend is not configured or not reachable, so this page shows sample data."
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#93370d]" /> Demo data
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
    <section className={`rounded-xl border border-line bg-surface p-4 md:p-5 ${className}`} aria-label={title}>
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

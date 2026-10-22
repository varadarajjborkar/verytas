"use client";

import Link from "next/link";
import type { Overview, Recurring, RuleHealth } from "@/lib/types";
import { HBars, Meter, Panel, Stat, TrendBars } from "./ui";

// Mid-tone hues that hold up on both the light and the dark surface.
const LEVEL_PALETTE = ["#e0604f", "#e0a04a", "#8aa6c4"];
const TREND_DAYS = 14;
// The API starts advising a rewrite at this ambiguity (api/insights.py).
export const UNCLEAR = 0.5;
const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);

export function DashboardView({ overview, recurring, health }: {
  overview: Overview;
  recurring: Recurring[];
  health: RuleHealth[];
}) {
  const levels = overview.findings.by_level;
  const published = overview.content.published ?? 0;
  const inFlight = (overview.content.in_review ?? 0) + (overview.content.changes_requested ?? 0);

  const trend = overview.trend.slice(-TREND_DAYS).map((d) => ({
    label: d.day.slice(5),
    values: [d.blocker, d.warning, d.advisory],
  }));
  const trendSeries = [
    { name: "Blockers", colour: LEVEL_PALETTE[0] },
    { name: "Warnings", colour: LEVEL_PALETTE[1] },
    { name: "Advisories", colour: LEVEL_PALETTE[2] },
  ];
  const categories = Object.entries(overview.findings.by_category)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([category, findings]) => ({ label: category, value: findings }));
  const unclear = health.filter((h) => h.ambiguity != null && h.ambiguity >= UNCLEAR).slice(0, 3);

  return (
    <div className="flex flex-col gap-5">
      <div className="vt-stagger grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Reviews" value={overview.reviews.total.toLocaleString()}
          hint={overview.reviews.failed ? `${overview.reviews.failed} failed` : undefined} />
        <Stat label="Findings" value={overview.findings.total.toLocaleString()} />
        <Stat label="Blockers caught" value={(levels.blocker ?? 0).toLocaleString()} />
        <Stat label="Fixes accepted" value={pct(overview.decisions.acceptance_rate)} />
        <Stat label="Published" value={published.toLocaleString()} hint={inFlight ? `${inFlight} in review` : undefined} />
      </div>

      <div className="grid gap-5">
        <Panel title="Findings, last 14 days">
          <div className="h-64">
            <TrendBars data={trend} series={trendSeries} />
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Where issues come from">
          <HBars data={categories} />
        </Panel>
        <Panel title="Busiest rules">
          <ul className="divide-y divide-line">
            {overview.top_rules.slice(0, 6).map((r) => (
              <li key={r.rule_id} className="flex items-center gap-3 py-2.5 text-sm first:pt-0 last:pb-0">
                <code className="w-28 shrink-0 truncate text-xs text-muted">{r.code}</code>
                <span className="min-w-0 flex-1 truncate" title={r.title}>{r.title}</span>
                <span className="tabular-nums">{r.findings}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Recurring phrases">
          <ul className="divide-y divide-line">
            {recurring.slice(0, 5).map((r) => (
              <li key={`${r.rule}-${r.phrase}`} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">&ldquo;{r.phrase}&rdquo;</p>
                  <p className="truncate text-xs text-subtle">{r.title}</p>
                </div>
                <p className="shrink-0 text-sm tabular-nums" title={`${r.count} times across ${r.reviews} reviews`}>{r.count}</p>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Rules that look unclear"
          aside={<Link href="/guidelines" className="text-xs font-medium text-accent hover:underline">View all</Link>}>
          {unclear.length === 0 ? (
            <p className="text-sm text-muted">Nothing stands out yet.</p>
          ) : (
            <ul className="flex flex-col gap-4">
              {unclear.map((h) => (
                <li key={h.rule_id}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3">
                    <p className="truncate text-sm font-medium">{h.title}</p>
                    <code className="shrink-0 text-xs text-subtle">{h.code}</code>
                  </div>
                  <Meter value={h.ambiguity ?? 0} label={`Ambiguity of ${h.code}`} tone="danger" />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

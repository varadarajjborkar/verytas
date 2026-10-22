"use client";

import { PieChart } from "@openuidev/react-ui";
import Link from "next/link";
import type { Overview, Recurring, RuleHealth } from "@/lib/types";
import { HBars, Meter, Panel, Stat, TrendBars } from "./ui";

const LEVEL_PALETTE = ["#b42318", "#dc6803", "#2e90fa"];
const STATUS_ORDER = ["draft", "in_review", "changes_requested", "approved", "published"];
const PIPELINE_PALETTE = ["#94a3b8", "#4f46e5", "#dc6803", "#16a34a", "#0e7490"];
const TREND_DAYS = 14;
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
    .slice(0, 8)
    .map(([category, findings]) => ({ category, findings }));
  const pipeline = STATUS_ORDER.filter((s) => overview.content[s]).map((s) => ({
    status: s.replace("_", " "),
    items: overview.content[s],
  }));
  const unclear = health.filter((h) => h.ambiguity != null && h.ambiguity >= 0.4).slice(0, 3);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Reviews run" value={overview.reviews.total.toLocaleString()}
              hint={`${overview.reviews.failed} failed and flagged, never passed`} />
        <Stat label="Findings" value={overview.findings.total.toLocaleString()}
              hint="every one cited to a rule or fact" />
        <Stat label="Blockers caught" value={(levels.blocker ?? 0).toLocaleString()}
              hint="stopped before publication" />
        <Stat label="Fix acceptance" value={pct(overview.decisions.acceptance_rate)}
              hint={`${overview.decisions.rejected ?? 0} overridden with a reason`} />
        <Stat label="Published" value={published.toLocaleString()} hint={`${inFlight} in review right now`} />
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <Panel title={`Findings over the last ${TREND_DAYS} days`} subtitle="Stacked by severity" className="xl:col-span-2">
          <div className="h-72">
            <TrendBars data={trend} series={trendSeries} />
          </div>
        </Panel>
        <Panel title="Content pipeline" subtitle="Where everything sits in the approval flow">
          <div className="flex h-72 flex-col">
            <div className="mx-auto aspect-square h-60 max-w-full shrink-0">
              <PieChart data={pipeline} categoryKey="status" dataKey="items" variant="donut" format="number"
                legend={false} customPalette={PIPELINE_PALETTE} />
            </div>
            <ul className="mt-3 flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs">
              {pipeline.map((p, i) => (
                <li key={p.status} className="inline-flex items-center gap-1.5 capitalize">
                  <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: PIPELINE_PALETTE[i % PIPELINE_PALETTE.length] }} />
                  {p.status} <span className="tabular-nums text-muted">{p.items}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="What goes wrong most" subtitle="Findings by check family">
          <HBars data={categories.map((c) => ({ label: c.category, value: c.findings }))} />
        </Panel>
        <Panel title="Rules that fire most" subtitle="Top rules by findings">
          {/* A plain table: it sizes to the card instead of pushing its last column out of view. */}
          <table className="w-full table-fixed text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted">
                <th className="w-[38%] py-2 pr-2 font-medium">Rule</th>
                <th className="py-2 pr-2 font-medium">What it checks</th>
                <th className="w-20 py-2 text-right font-medium">Findings</th>
              </tr>
            </thead>
            <tbody>
              {overview.top_rules.slice(0, 8).map((r) => (
                <tr key={r.rule_id} className="border-b border-line last:border-0">
                  <td className="truncate py-2 pr-2"><code className="text-xs">{r.code}</code></td>
                  <td className="truncate py-2 pr-2" title={r.title}>{r.title}</td>
                  <td className="py-2 text-right tabular-nums">{r.findings}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel title="Recurring problems" subtitle="Same rule, same phrase, many pieces of content: a training or template fix">
          <ul className="divide-y divide-line">
            {recurring.slice(0, 6).map((r) => (
              <li key={`${r.rule}-${r.phrase}`} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">&ldquo;{r.phrase}&rdquo;</p>
                  <p className="text-xs text-muted"><code>{r.rule}</code> {r.title}</p>
                </div>
                <p className="shrink-0 text-right text-sm tabular-nums">
                  {r.count}
                  <span className="block text-xs text-muted">in {r.reviews} reviews</span>
                </p>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Guidelines that look unclear" subtitle="From reviewer overrides and disagreement, not from the model">
          {unclear.length === 0 ? (
            <p className="text-sm text-muted">No rule has enough overrides to look ambiguous yet.</p>
          ) : (
            <ul className="flex flex-col gap-4">
              {unclear.map((h) => (
                <li key={h.rule_id}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <p className="text-sm font-medium"><code className="text-xs">{h.code}</code> {h.title}</p>
                    <p className="text-xs text-muted">{h.decisions} decisions</p>
                  </div>
                  <Meter value={h.ambiguity ?? 0} label={`Ambiguity of ${h.code}`} tone="danger" />
                  {h.advice[0] && <p className="mt-1 text-xs text-muted">{h.advice[0]}</p>}
                </li>
              ))}
            </ul>
          )}
          <Link href="/guidelines" className="mt-4 inline-block text-sm font-medium text-accent hover:underline">
            Open guideline health
          </Link>
        </Panel>
      </div>
    </div>
  );
}

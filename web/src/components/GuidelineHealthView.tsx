"use client";

import { BarChart } from "@openuidev/react-ui";
import type { RuleHealth } from "@/lib/types";
import { Details, Meter, Panel } from "./ui";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function GuidelineHealthView({ health }: { health: RuleHealth[] }) {
  const scored = health.filter((h) => h.enough_data && h.ambiguity != null);
  const pending = health.filter((h) => !h.enough_data);
  const bars = scored.map((h) => ({
    rule: h.code,
    "Overridden %": Math.round(h.override_rate * 100),
    "Disagreement %": Math.round(h.reviewer_disagreement * 100),
  }));

  return (
    <div className="flex flex-col gap-5">
      <Panel title="Overrides and disagreement by rule">
        <div className="h-72">
          {bars.length > 0 ? (
            <BarChart data={bars} categoryKey="rule" variant="grouped" customPalette={["#e0604f", "#3d8bf2"]} />
          ) : (
            <p className="text-sm text-muted">Not enough decisions to plot yet.</p>
          )}
        </div>
      </Panel>

      <Panel title="Most ambiguous first">
        <ul className="vt-stagger flex flex-col gap-3">
          {scored.map((h) => (
            <li key={h.rule_id} className="rounded-xl border border-line bg-raised p-4">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] lg:items-center">
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <p className="truncate text-sm font-medium">{h.title}</p>
                    <code className="shrink-0 text-xs text-subtle">{h.code}</code>
                  </div>
                  <div className="mt-2.5 max-w-sm">
                    <Meter value={h.ambiguity ?? 0} label={`Ambiguity of ${h.code}`} tone={(h.ambiguity ?? 0) >= 0.4 ? "danger" : "accent"} />
                  </div>
                </div>
                <dl className="grid grid-cols-3 gap-3 text-xs">
                  <div><dt className="text-subtle">Overridden</dt><dd className="mt-0.5 text-sm tabular-nums">{pct(h.override_rate)}</dd></div>
                  <div><dt className="text-subtle">Unclear</dt><dd className="mt-0.5 text-sm tabular-nums">{pct(h.unclear_share)}</dd></div>
                  <div><dt className="text-subtle">Agreement</dt><dd className="mt-0.5 text-sm tabular-nums">{pct(h.agreement_posterior.mean)}</dd></div>
                </dl>
              </div>
              {h.advice[0] && (
                <p className="mt-3 rounded-lg bg-sunken px-3 py-2 text-xs leading-5 text-muted">
                  {h.advice[0][0].toUpperCase() + h.advice[0].slice(1)}
                </p>
              )}
            </li>
          ))}
        </ul>
        {pending.length > 0 && (
          <p className="mt-4 text-xs text-subtle">Waiting for more decisions: {pending.map((h) => h.code).join(", ")}</p>
        )}
      </Panel>

      <Details summary="How the score works">
        <dl className="grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-medium">Overridden <span className="text-subtle">40%</span></dt>
            <dd className="mt-0.5 text-muted">Share of the rule&apos;s findings reviewers rejected.</dd>
          </div>
          <div>
            <dt className="font-medium">Unclear <span className="text-subtle">35%</span></dt>
            <dd className="mt-0.5 text-muted">Rejections where the reviewer said the rule itself is unclear.</dd>
          </div>
          <div>
            <dt className="font-medium">Disagreement <span className="text-subtle">25%</span></dt>
            <dd className="mt-0.5 text-muted">Gap between reviewers&apos; acceptance rates on the same rule.</dd>
          </div>
          <div>
            <dt className="font-medium">Agreement</dt>
            <dd className="mt-0.5 text-muted">Beta(1 + accepted, 1 + rejected), so 3 decisions aren&apos;t judged like 300.</dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-subtle">Nothing changes automatically. An admin reads the advice and edits the rule.</p>
      </Details>
    </div>
  );
}

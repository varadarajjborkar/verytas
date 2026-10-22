"use client";

import { BarChart } from "@openuidev/react-ui";
import type { RuleHealth } from "@/lib/types";
import { Meter, Panel } from "./ui";

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function GuidelineHealthView({ health }: { health: RuleHealth[] }) {
  const scored = health.filter((h) => h.enough_data && h.ambiguity != null);
  const pending = health.filter((h) => !h.enough_data);
  const bars = scored.map((h) => ({
    rule: h.code,
    "Override rate %": Math.round(h.override_rate * 100),
    "Disagreement %": Math.round(h.reviewer_disagreement * 100),
  }));

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 xl:grid-cols-3">
        <Panel title="How the ambiguity score works" subtitle="Computed from human decisions only" className="xl:col-span-1">
          <dl className="space-y-3 text-sm">
            <div>
              <dt className="font-medium">Override rate <span className="text-muted">(40%)</span></dt>
              <dd className="text-muted">Share of the rule&apos;s findings that reviewers rejected.</dd>
            </div>
            <div>
              <dt className="font-medium">&ldquo;Guideline unclear&rdquo; share <span className="text-muted">(35%)</span></dt>
              <dd className="text-muted">Rejections where the reviewer said the rule itself is unclear.</dd>
            </div>
            <div>
              <dt className="font-medium">Reviewer disagreement <span className="text-muted">(25%)</span></dt>
              <dd className="text-muted">Gap between reviewers&apos; acceptance rates on the same rule.</dd>
            </div>
            <div>
              <dt className="font-medium">Agreement posterior</dt>
              <dd className="text-muted">
                Beta(1 + accepted, 1 + rejected). The lower bound tells you how sure we are that reviewers agree
                with the rule, so a rule with 3 decisions is not judged like one with 300.
              </dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-muted">Nothing changes automatically. A brand admin reads the advice and edits the rule.</p>
        </Panel>
        <Panel title="Override and disagreement by rule" subtitle="Tall pairs of bars mean reviewers override the rule and disagree about it" className="xl:col-span-2">
          <div className="h-80">
            {bars.length > 0 ? (
              <BarChart data={bars} categoryKey="rule" variant="grouped" customPalette={["#b42318", "#4f46e5"]} />
            ) : (
              <p className="text-sm text-muted">Not enough decided rules to plot yet.</p>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Rules ranked by ambiguity" subtitle="Highest first">
        <ul className="divide-y divide-line">
          {scored.map((h) => (
            <li key={h.rule_id} className="grid gap-3 py-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.2fr)] lg:items-start">
              <div>
                <p className="text-sm font-medium">
                  <code className="text-xs">{h.code}</code> {h.title}
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  severity {h.severity} · {h.findings} findings · {h.accepted} accepted · {h.rejected} overridden
                </p>
                <div className="mt-2 max-w-xs">
                  <Meter value={h.ambiguity ?? 0} label={`Ambiguity of ${h.code}`} tone={(h.ambiguity ?? 0) >= 0.4 ? "danger" : "accent"} />
                </div>
              </div>
              <dl className="grid grid-cols-3 gap-3 text-xs">
                <div><dt className="text-muted">Override rate</dt><dd className="tabular-nums">{pct(h.override_rate)}</dd></div>
                <div><dt className="text-muted">Unclear share</dt><dd className="tabular-nums">{pct(h.unclear_share)}</dd></div>
                <div>
                  <dt className="text-muted">Agreement</dt>
                  <dd className="tabular-nums">{pct(h.agreement_posterior.mean)} (≥ {pct(h.agreement_posterior.lower_90)})</dd>
                </div>
              </dl>
              <div className="flex flex-col gap-2">
                {h.advice.length === 0 ? (
                  <p className="text-xs text-muted">Healthy: reviewers mostly agree with this rule.</p>
                ) : (
                  h.advice.map((a) => (
                    <p key={a} className="rounded-md border-l-2 border-[var(--vt-warning)] bg-[var(--vt-warning-bg)] px-2.5 py-1.5 text-xs text-[var(--vt-warning)]">
                      {a[0].toUpperCase() + a.slice(1)}
                    </p>
                  ))
                )}
              </div>
            </li>
          ))}
        </ul>
        {pending.length > 0 && (
          <p className="mt-4 text-xs text-muted">
            Waiting for more decisions before scoring: {pending.map((h) => h.code).join(", ")}.
          </p>
        )}
      </Panel>
    </div>
  );
}

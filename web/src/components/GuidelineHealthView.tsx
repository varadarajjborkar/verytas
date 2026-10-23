"use client";

import type { RuleHealth } from "@/lib/types";
import { ClarifyRule } from "./ClarifyRule";
import { UNCLEAR } from "./dashboard/widgets";
import { InfoPopover } from "./InfoPopover";
import { Meter, Panel, RuleCode } from "./ui";

// Mirrors MIN_DECISIONS in the API: fewer calls than this and a rate means nothing.
const MIN = 3;
const pct = (v: number) => `${Math.round(v * 100)}%`;

export function GuidelineHealthView({ health, canEdit = false }: { health: RuleHealth[]; canEdit?: boolean }) {
  const scored = health.filter((h) => h.enough_data && h.ambiguity != null);
  const pending = health.filter((h) => !h.enough_data);
  return (
    <div className="flex flex-col gap-5">
      {scored.length === 0 && (
        <p className="vt-card px-5 py-4 text-sm text-muted">
          A rule is scored once reviewers have confirmed or dismissed {MIN} of its findings. Dismissals with
          &ldquo;the guideline is unclear&rdquo; count the most.
        </p>
      )}

      <Panel title="Most ambiguous first" aside={<InfoPopover label="How it's scored">
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
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
        <p className="mt-4 text-xs text-subtle">Nothing changes automatically. An admin reads the advice, can have a clearer wording drafted from the rule&apos;s own cases, and decides whether to apply it.</p>
      </InfoPopover>}>
        <ul className="vt-stagger flex flex-col gap-3">
          {scored.map((h) => (
            <li key={h.rule_id} className="border-b border-line pb-4 last:border-0 last:pb-0">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] lg:items-center">
                <div className="min-w-0">
                  <div className="flex items-baseline gap-2">
                    <p className="truncate text-sm font-medium">{h.title}</p>
                    <RuleCode code={h.code} />
                  </div>
                  <div className="mt-2.5 max-w-sm">
                    <Meter value={h.ambiguity ?? 0} label={`Ambiguity of ${h.code}`} tone={(h.ambiguity ?? 0) >= UNCLEAR ? "danger" : "accent"} />
                  </div>
                </div>
                <dl className="grid grid-cols-3 gap-3 text-xs">
                  <div><dt className="text-subtle">Overridden</dt><dd className="mt-0.5 text-sm tabular-nums">{pct(h.override_rate)}</dd></div>
                  <div><dt className="text-subtle">Unclear</dt><dd className="mt-0.5 text-sm tabular-nums">{pct(h.unclear_share)}</dd></div>
                  <div><dt className="text-subtle">Agreement</dt><dd className="mt-0.5 text-sm tabular-nums">{pct(h.agreement_posterior.mean)}</dd></div>
                </dl>
              </div>
              {h.advice[0] && (
                <p className="mt-3 border-l-2 border-accent/50 pl-3 text-xs leading-5 text-muted">
                  {h.advice[0][0].toUpperCase() + h.advice[0].slice(1)}
                </p>
              )}
              {/* Only where a draft can work: a model-judged rule (word lists are edited directly) with cases. */}
              {canEdit && h.kind === "semantic" && h.decisions >= 2
                && h.advice.some((a) => a.startsWith("clarify") || a.startsWith("add a good")) && (
                <ClarifyRule ruleId={h.rule_id} code={h.code} />
              )}
            </li>
          ))}
        </ul>
        {scored.length === 0 && <p className="text-sm text-muted">No rule has enough decisions yet.</p>}
        {pending.length > 0 && (
          <div className="mt-4 border-t border-line pt-3">
            <p className="text-xs text-subtle">Waiting for more decisions</p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {pending.map((h) => (
                <li key={h.rule_id} title={`${h.title}: ${h.decisions} of ${MIN} decisions`}
                  className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[11px] text-muted">
                  {h.code} <span className="font-sans tabular-nums text-subtle">{h.decisions}/{MIN}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Panel>

    </div>
  );
}

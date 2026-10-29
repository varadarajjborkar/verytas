"use client";

import Link from "next/link";
import { useId, useState, type CSSProperties } from "react";
import type { RuleHealth } from "@/lib/types";
import { ClarifyRule } from "./ClarifyRule";
import { UNCLEAR } from "./dashboard/widgets";
import { AlertIcon, CheckIcon, OctagonIcon } from "./Icons";
import { InfoPopover } from "./InfoPopover";
import { Panel, RuleCode } from "./ui";

// Mirrors MIN_DECISIONS in the API: fewer calls than this and a rate means nothing.
const MIN = 3;
// Under UNCLEAR the API gives no rewrite advice; from here up a rule is still worth a look.
const SOMEWHAT = 0.25;

type Level = "bad" | "mid" | "good";
const LEVELS: Level[] = ["bad", "mid", "good"];
const LEVEL: Record<Level, { word: string; Icon: typeof OctagonIcon; pill: string; base: string; hi: string }> = {
  bad: { word: "Confusing", Icon: OctagonIcon, pill: "bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)]",
    base: "var(--vt-ring-bad)", hi: "var(--vt-ring-bad-hi)" },
  mid: { word: "A bit unclear", Icon: AlertIcon, pill: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
    base: "var(--vt-ring-mid)", hi: "var(--vt-ring-mid-hi)" },
  good: { word: "Clear", Icon: CheckIcon, pill: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
    base: "var(--vt-ring-good)", hi: "var(--vt-ring-good-hi)" },
};
const levelOf = (ambiguity: number): Level => (ambiguity >= UNCLEAR ? "bad" : ambiguity >= SOMEWHAT ? "mid" : "good");
const rules = (n: number) => `${n} rule${n === 1 ? "" : "s"}`;
const pct = (v: number) => `${Math.round(v * 100)}%`;

function LevelTag({ level }: { level: Level }) {
  const { word, Icon, pill } = LEVEL[level];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-semibold ${pill}`}>
      <Icon size={12} strokeWidth={2.25} />{word}
    </span>
  );
}

/**
 * How clear the brand's rules are, as a tilted ring of three levels. A slice or a row picks a level and
 * narrows the list beside it to that level's rules; each rule opens in the Brand library. Under each rule
 * are the numbers behind its level and the advice, and an admin can have a clearer wording drafted there.
 */
export function GuidelineHealthView({ health, canEdit = false }: { health: RuleHealth[]; canEdit?: boolean }) {
  const scored = health.filter((h) => h.enough_data && h.ambiguity != null)
    .sort((a, b) => (b.ambiguity ?? 0) - (a.ambiguity ?? 0));
  const pending = health.filter((h) => !h.enough_data);
  const groups: Record<Level, RuleHealth[]> = { bad: [], mid: [], good: [] };
  for (const h of scored) groups[levelOf(h.ambiguity ?? 0)].push(h);
  const total = scored.length;
  const share = (k: Level) => Math.round((groups[k].length / Math.max(total, 1)) * 100);

  const [chosen, setPicked] = useState<Level | null>(null);
  // A refresh can empty the chosen level; the view then shows every level again rather than nothing.
  const picked = chosen && groups[chosen].length > 0 ? chosen : null;
  // A row under the pointer lifts its slice too, so the list and the ring read as one.
  const [hot, setHot] = useState<Level | null>(null);
  const [said, setSaid] = useState<Level | null>(null);
  const pick = (k: Level) => setPicked(picked === k ? null : k);

  return (
    <Panel title="How clear are your rules?" aside={<InfoPopover label="How it's scored">
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
      <p className="mt-4 text-xs text-subtle">
        Together they make a rule&apos;s ambiguity. {Math.round(UNCLEAR * 100)}% or more is Confusing, {Math.round(SOMEWHAT * 100)}% or
        more is A bit unclear, anything lower is Clear. Nothing changes automatically: an admin reads the advice,
        can have a clearer wording drafted from the rule&apos;s own cases, and decides whether to apply it.
      </p>
    </InfoPopover>}>
      {total === 0 ? (
        <p className="text-sm text-muted">
          A rule is scored once reviewers have confirmed or dismissed {MIN} of its findings. Dismissals with
          &ldquo;the guideline is unclear&rdquo; count the most.
        </p>
      ) : (
        <div className="grid gap-5 md:grid-cols-[minmax(0,320px)_minmax(0,1fr)] md:items-start md:gap-8">
          <div className="min-w-0">
            <Ring groups={groups} total={total} picked={picked} hot={hot} onPick={pick} onSay={setSaid} />
            <p aria-live="polite" className="mt-1.5 min-h-5 text-center text-xs text-muted">
              {said && <><b className="font-semibold text-ink">{LEVEL[said].word}</b>: {groups[said].length} of {total} rules ({share(said)}%)</>}
            </p>
            <ul className="mt-2 border-t border-line">
              {LEVELS.map((k) => (
                <li key={k} className="border-b border-line last:border-0">
                  <button type="button" aria-pressed={picked === k} disabled={groups[k].length === 0} onClick={() => pick(k)}
                    onMouseEnter={() => { setHot(k); setSaid(k); }} onMouseLeave={() => { setHot(null); setSaid(null); }}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-1 py-2 text-left transition-colors hover:bg-sunken disabled:cursor-default disabled:opacity-60 disabled:hover:bg-transparent aria-pressed:bg-sunken">
                    <LevelTag level={k} />
                    <span className="whitespace-nowrap text-[13px] font-semibold tabular-nums">
                      {rules(groups[k].length)}<span className="ml-1.5 text-xs font-normal text-muted">{share(k)}%</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="flex min-w-0 flex-col gap-2.5">
            {/* Levels not picked are hidden, not unmounted, so a clearer wording being drafted under one survives a look at another. */}
            {LEVELS.filter((k) => groups[k].length > 0).map((k) => (
              <section key={k} aria-label={`${LEVEL[k].word} rules`} hidden={picked != null && picked !== k}
                className="rounded-xl border border-line bg-raised px-3 py-2.5">
                <h3 className="mb-1 flex items-center gap-2 text-[13px] font-medium text-subtle"><LevelTag level={k} />{rules(groups[k].length)}</h3>
                <ul>
                  {groups[k].map((h) => (
                    <li key={h.rule_id} className="border-b border-line/60 pb-1 last:border-0 last:pb-0">
                      {/* An event's rules are kept with the event, not in the rules list. */}
                      <Link href={h.event_id != null ? "/library?tab=events" : `/library?q=${encodeURIComponent(h.code)}`} aria-label={`Open rule: ${h.title}`}
                        className="flex items-center gap-2.5 rounded-md p-1.5 text-[13px] transition-colors hover:bg-sunken">
                        <span className="min-w-0 flex-1 truncate" title={h.title}>{h.title}</span>
                        <RuleCode code={h.code} className="hidden max-w-[11rem] sm:block" />
                        <span className="shrink-0 text-xs font-medium text-accent">Open</span>
                      </Link>
                      {/* The why behind the level, outside the link: the draft below is a control of its own. */}
                      <div className="px-1.5 pb-1.5">
                        <p className="text-xs tabular-nums text-subtle">
                          Overridden {pct(h.override_rate)} · Unclear {pct(h.unclear_share)} · Agreement {pct(h.agreement_posterior.mean)}
                        </p>
                        {h.advice[0] && (
                          <p className="mt-1.5 border-l-2 border-accent/50 pl-3 text-xs leading-5 text-muted">
                            {h.advice[0][0].toUpperCase() + h.advice[0].slice(1)}
                          </p>
                        )}
                        {/* Only where a draft can work: a model-judged rule (word lists are edited directly) with cases. */}
                        {canEdit && h.kind === "semantic" && h.decisions >= 2
                          && h.advice.some((a) => a.startsWith("clarify") || a.startsWith("add a good")) && (
                          <ClarifyRule ruleId={h.rule_id} code={h.code} />
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
            {picked && (
              <button type="button" onClick={() => setPicked(null)} className="vt-btn vt-btn-sm self-start">Show all rules</button>
            )}
          </div>
        </div>
      )}

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
  );
}

// The ring's geometry, in the SVG's own units: tilt (how flat the circle looks), depth, outer and inner radius.
const TILT = 0.56, DEPTH = 26, R = 116, HOLE = R * 0.56, CX = 150, CY = 8 + R * TILT;
const W = 300, H = Math.ceil(CY + R * TILT + DEPTH + 22);
// Angles on screen: 0 is right, π/2 is the near edge. Confusing starts at 20° and the levels run clockwise,
// so the two that need work face the reader.
const START = (20 * Math.PI) / 180;
const POP = 8, RISE = 7;

const at = (radius: number, a: number, dy = 0) =>
  `${(CX + radius * Math.cos(a)).toFixed(2)} ${(CY + radius * TILT * Math.sin(a) + dy).toFixed(2)}`;
const shade = (k: Level, pct: number) => `color-mix(in srgb, ${LEVEL[k].base} ${pct}%, var(--vt-ring-shade))`;

/** The parts of [a0, a1] inside [lo, lo + π], any turn round: the near half for outer sides, the far half for the inner one. */
function within(a0: number, a1: number, lo: number): [number, number][] {
  const out: [number, number][] = [];
  for (let n = -1; n <= 2; n++) {
    const s = Math.max(a0, lo + n * 2 * Math.PI), e = Math.min(a1, lo + n * 2 * Math.PI + Math.PI);
    if (e - s > 1e-3) out.push([s, e]);
  }
  return out;
}

/** A side of the ring between two angles at one radius, dropped by DEPTH. */
const side = (radius: number, a: number, b: number) =>
  `M ${at(radius, a)} A ${radius} ${radius * TILT} 0 0 1 ${at(radius, b)} L ${at(radius, b, DEPTH)} A ${radius} ${radius * TILT} 0 0 0 ${at(radius, a, DEPTH)} Z`;

function Ring({ groups, total, picked, hot, onPick, onSay }: {
  groups: Record<Level, RuleHealth[]>; total: number; picked: Level | null; hot: Level | null;
  onPick: (k: Level) => void; onSay: (k: Level | null) => void;
}) {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const present = LEVELS.filter((k) => groups[k].length > 0);
  const slices = present.map((k, i) => {
    const before = present.slice(0, i).reduce((n, j) => n + groups[j].length, 0);
    const a0 = START + (before / total) * 2 * Math.PI, span = (groups[k].length / total) * 2 * Math.PI;
    return { k, a0, a1: a0 + span, mid: a0 + span / 2, span };
  });
  const clear = groups.good.length;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="group" data-dim={picked ? "true" : undefined}
      aria-label={`${clear} of ${total} rules are clear. ${LEVELS.map((k) => `${LEVEL[k].word}: ${groups[k].length}`).join(", ")}.`}
      className="vt-ring mx-auto block h-auto w-full max-w-[320px] overflow-visible">
      <defs>
        <filter id={`${uid}-floor`} x="-20%" y="-50%" width="140%" height="200%"><feGaussianBlur stdDeviation="9" /></filter>
        {LEVELS.map((k) => (
          <g key={k}>
            <linearGradient id={`${uid}-top-${k}`} gradientUnits="userSpaceOnUse" x1="0" y1={CY - R * TILT} x2="0" y2={CY + R * TILT}>
              <stop offset="0" style={{ stopColor: LEVEL[k].hi }} /><stop offset="1" style={{ stopColor: LEVEL[k].base }} />
            </linearGradient>
            <linearGradient id={`${uid}-side-${k}`} gradientUnits="userSpaceOnUse" x1={CX - R} y1="0" x2={CX + R} y2="0">
              <stop offset="0" style={{ stopColor: shade(k, 48) }} /><stop offset="0.42" style={{ stopColor: shade(k, 76) }} />
              <stop offset="1" style={{ stopColor: shade(k, 44) }} />
            </linearGradient>
          </g>
        ))}
      </defs>
      <ellipse cx={CX} cy={CY + DEPTH + 8} rx={R * 0.98} ry={R * TILT * 0.82} style={{ fill: "var(--vt-ring-floor)" }} filter={`url(#${uid}-floor)`} />

      {/* Far slices first, so nearer ones cover them. */}
      {[...slices].sort((p, q) => Math.sin(p.mid) - Math.sin(q.mid)).map((s) => {
        const n = groups[s.k].length, pct = Math.round((n / total) * 100);
        const lx = CX + ((R + HOLE) / 2) * Math.cos(s.mid), ly = CY + ((R + HOLE) / 2) * TILT * Math.sin(s.mid) + 6;
        const lift = { "--dx": `${(Math.cos(s.mid) * POP).toFixed(1)}px`, "--dy": `${(Math.sin(s.mid) * POP * TILT - RISE).toFixed(1)}px` } as CSSProperties;
        const press = () => onPick(s.k);
        // A level holding every rule is a whole ring: two ellipses, no cut ends and no radial seam at START.
        const full = s.span > 2 * Math.PI - 1e-6;
        const top = full
          ? `M ${at(R, 0)} A ${R} ${R * TILT} 0 1 1 ${at(R, Math.PI)} A ${R} ${R * TILT} 0 1 1 ${at(R, 0)} Z
             M ${at(HOLE, 0)} A ${HOLE} ${HOLE * TILT} 0 1 1 ${at(HOLE, Math.PI)} A ${HOLE} ${HOLE * TILT} 0 1 1 ${at(HOLE, 0)} Z`
          : `M ${at(R, s.a0)} A ${R} ${R * TILT} 0 0 1 ${at(R, s.mid)} A ${R} ${R * TILT} 0 0 1 ${at(R, s.a1)} L ${at(HOLE, s.a1)}
             A ${HOLE} ${HOLE * TILT} 0 0 0 ${at(HOLE, s.mid)} A ${HOLE} ${HOLE * TILT} 0 0 0 ${at(HOLE, s.a0)} Z`;
        // The walls in view: the near half of the outside and the far half of the inside, each one piece on a whole ring.
        const near = full ? [[0, Math.PI] as [number, number]] : within(s.a0, s.a1, 0);
        const far = full ? [[Math.PI, 2 * Math.PI] as [number, number]] : within(s.a0, s.a1, Math.PI);
        return (
          <g key={s.k} className="vt-ring-slice" style={lift} role="button" tabIndex={0} aria-pressed={picked === s.k}
            aria-label={`${LEVEL[s.k].word}: ${n} of ${total} rules, ${pct}%. Show them`}
            data-on={picked === s.k ? "true" : undefined} data-hot={hot === s.k ? "true" : undefined}
            onClick={press} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); press(); } }}
            onMouseEnter={() => onSay(s.k)} onMouseLeave={() => onSay(null)} onFocus={() => onSay(s.k)} onBlur={() => onSay(null)}>
            {/* The still hit area: the top and the near side at rest. */}
            <path className="vt-ring-hit" d={top} fillRule="evenodd" />
            {near.map(([x, y]) => <path key={`hit${x}`} className="vt-ring-hit" d={side(R, x, y)} />)}
            <g className="vt-ring-lift">
              {far.map(([x, y]) => <path key={`in${x}`} d={side(HOLE, x, y)} style={{ fill: shade(s.k, 62) }} />)}
              {!full && [s.a0, s.a1].map((x) => (
                <path key={`cut${x}`} className="vt-ring-cut" d={`M ${at(HOLE, x)} L ${at(R, x)} L ${at(R, x, DEPTH)} L ${at(HOLE, x, DEPTH)} Z`} style={{ fill: shade(s.k, 58) }} />
              ))}
              {near.map(([x, y]) => (
                <path key={`out${x}`} d={side(R, x, y)} fill={`url(#${uid}-side-${s.k})`} style={{ stroke: "var(--vt-raised)" }} strokeWidth={1.2} strokeLinejoin="round" />
              ))}
              <path className="vt-ring-top" d={top} fillRule="evenodd" fill={`url(#${uid}-top-${s.k})`} style={{ stroke: "var(--vt-raised)" }} strokeWidth={1.5} strokeLinejoin="round" />
              {/* Too thin a slice has no room for its number; the row under the ring carries it. */}
              {s.span > 0.35 && (
                <text x={lx.toFixed(1)} y={ly.toFixed(1)} textAnchor="middle" pointerEvents="none" paintOrder="stroke"
                  style={{ fill: "var(--vt-ring-label)", stroke: "var(--vt-ring-halo)" }} strokeWidth={3} strokeLinejoin="round" fontSize={16} fontWeight={600}>
                  {n}<tspan dx={3} fontSize={11}>{pct}%</tspan>
                </text>
              )}
            </g>
          </g>
        );
      })}

      <g pointerEvents="none">
        <text x={CX} y={CY + 12} textAnchor="middle" style={{ fill: "var(--vt-ink)" }} fontSize={24} fontWeight={600} letterSpacing={-0.5}>
          {clear}<tspan dx={2} fontSize={13} style={{ fill: "var(--vt-subtle)" }}>/ {total}</tspan>
        </text>
        <text x={CX} y={CY + 26} textAnchor="middle" style={{ fill: "var(--vt-muted)" }} fontSize={10.5} fontWeight={500}>rules are clear</text>
      </g>
    </svg>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { TrackPoint } from "@/lib/types";

const H = 220;
const PAD = { left: 34, right: 14, top: 14, bottom: 28 };
const STATUS_LABEL: Record<string, string> = {
  draft: "Draft", in_review: "Waiting for review", changes_requested: "Sent back", approved: "Approved",
  published: "Published", withdrawn: "Withdrawn",
};
const LEVEL = {
  blocker: { label: "Must-fix", color: "var(--vt-blocker)" },
  warning: { label: "Should-fix", color: "var(--vt-warning)" },
  advisory: { label: "Note", color: "var(--vt-advisory)" },
  none: { label: "On brand", color: "var(--vt-ok)" },
} as const;

const worst = (p: TrackPoint) => (p.blockers ? "blocker" : p.warnings ? "warning" : p.advisories ? "advisory" : "none");
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/**
 * One creator's pieces in the order they sent them, by distance from the brand as sent.
 * A creator who stays on brand draws a flat line along zero; drift shows as the line lifting.
 * Points are coloured by their worst finding (with the label in the tooltip and legend, never
 * colour alone), ringed when the finding was tone or topic drift, and open the piece on click.
 */
export function DriftChart({ points }: { points: TrackPoint[] }) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);
  const router = useRouter();

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (!points.length) {
    return <p className="rounded-xl bg-sunken px-4 py-8 text-center text-sm text-muted">Nothing reviewed yet. The line starts with their first piece.</p>;
  }
  const plotW = width - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (d: number) => PAD.top + plotH - (d / 100) * plotH;
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.distance).toFixed(1)}`).join(" ");
  const hit = Math.max(10, Math.min(18, plotW / points.length / 2));
  const a = active == null ? null : points[active];

  return (
    <div className="flex flex-col gap-3">
      <div ref={box} className="relative" onMouseLeave={() => setActive(null)}>
        <svg width={width} height={H} role="img" aria-label={`Distance from the brand across ${points.length} pieces`} className="block overflow-visible">
          {[0, 50, 100].map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--vt-line)" strokeDasharray={v ? "2 4" : undefined} />
              <text x={PAD.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-[var(--vt-subtle)] text-[10px] tabular-nums">{v}</text>
            </g>
          ))}
          {a && <line x1={x(active!)} x2={x(active!)} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--vt-line-strong)" />}
          <path d={path} fill="none" stroke="var(--vt-accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" pathLength={1} className="vt-draw" />
          {points.map((p, i) => {
            const lv = LEVEL[worst(p)];
            const href = `/review?id=${p.content_id}`;
            return (
              <a key={p.content_id} href={href} aria-label={`${p.title}, ${day(p.at)}: ${p.summary}`}
                onClick={(e) => { e.preventDefault(); router.push(href); }}
                onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
                className="cursor-pointer outline-none">
                <circle cx={x(i)} cy={y(p.distance)} r={hit} fill="transparent" />
                {p.drift.length > 0 && <circle cx={x(i)} cy={y(p.distance)} r={8.5} fill="none" stroke={lv.color} strokeWidth={1.5} />}
                <circle cx={x(i)} cy={y(p.distance)} r={active === i ? 6 : 4.5} fill={lv.color} stroke="var(--vt-raised)" strokeWidth={2}
                  className="transition-[r] duration-150" />
              </a>
            );
          })}
          {[0, points.length - 1].filter((i, n, all) => all.indexOf(i) === n).map((i) => (
            <text key={i} x={x(i)} y={H - 8} textAnchor={points.length === 1 ? "middle" : i ? "end" : "start"} className="fill-[var(--vt-subtle)] text-[10px]">
              {day(points[i].at)}
            </text>
          ))}
        </svg>
        {a && (
          <div role="tooltip" className="vt-pop pointer-events-none absolute z-10 w-[min(18rem,calc(100%-1rem))] rounded-xl border border-line bg-raised p-3 text-xs shadow-[var(--vt-shadow-pop)]"
            style={{
              left: Math.min(Math.max(0, x(active!) - 144), width - Math.min(288, width - 16)),
              top: y(a.distance) > H / 2 ? Math.max(0, y(a.distance) - 12) : y(a.distance) + 14,
              transform: y(a.distance) > H / 2 ? "translateY(-100%)" : undefined,
            }}>
            <p className="font-semibold text-ink">{a.title}</p>
            <p className="mt-0.5 text-subtle">{day(a.at)} · {a.channel}{a.event ? ` · ${a.event}` : ""} · {STATUS_LABEL[a.status] ?? a.status}</p>
            <p className="mt-2 text-muted">{a.summary}</p>
            {a.issues.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1">
                {a.issues.map((f, n) => (
                  <li key={n} className="flex items-baseline gap-1.5">
                    <span className="inline-block h-2 w-2 shrink-0 translate-y-[-1px] rounded-full" style={{ background: LEVEL[f.level].color }} aria-hidden />
                    <span><span className="text-subtle">{LEVEL[f.level].label}:</span> {f.title}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 font-medium text-accent">{a.distance ? `${a.distance} from the brand` : "On the line"} · click to open</p>
          </div>
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted" aria-label="Legend">
        {(["none", "advisory", "warning", "blocker"] as const).map((k) => (
          <li key={k} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: LEVEL[k].color }} aria-hidden />{LEVEL[k].label}</li>
        ))}
        <li className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-[1.5px] border-[var(--vt-muted)]" aria-hidden />Tone or topic drift</li>
      </ul>
    </div>
  );
}

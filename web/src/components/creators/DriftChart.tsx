"use client";

import { useRouter } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";
import type { TrackPoint } from "@/lib/types";
import { channelName } from "@/lib/channels";

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
 * colour alone), ringed when the finding was tone or topic drift, and open the piece on click. On touch,
 * the first tap shows why and the second opens; modifier-clicks open a new tab as links do.
 */
export function DriftChart({ points }: { points: TrackPoint[] }) {
  const box = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<number | null>(null);
  // The last point pointed at, where the crosshair rests while it fades. The glide is off for the first
  // frame of each hover, so the crosshair and tooltip appear at the point instead of sliding in.
  const [shown, setShown] = useState(0);
  const [glide, setGlide] = useState(false);
  const pick = (i: number | null) => {
    if (i != null && active == null) {
      setGlide(false);
      requestAnimationFrame(() => requestAnimationFrame(() => setGlide(true)));
    }
    setActive(i);
    if (i != null) setShown(i);
  };
  const [width, setWidth] = useState(640);
  const [focused, setFocused] = useState<number | null>(null);
  const [touch, setTouch] = useState(false);
  const router = useRouter();

  // Measured before paint, so the first frame is drawn at the real width rather than a guess.
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    setWidth(Math.max(200, el.clientWidth));
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(200, Math.round(e.contentRect.width))));
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
      <div ref={box} className="relative" onMouseLeave={() => pick(null)}
        onKeyDown={(e) => { if (e.key === "Escape") pick(null); }}>
        {/* A group, not an image: the points inside are links that assistive tech must reach. */}
        <svg width={width} height={H} role="group" aria-label={`Distance from the brand across ${points.length} pieces`} className="block overflow-visible">
          {[0, 50, 100].map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--vt-line)" strokeDasharray={v ? "2 4" : undefined} />
              <text x={PAD.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-[var(--vt-subtle)] text-[11px] tabular-nums">{v}</text>
            </g>
          ))}
          {/* Drawn at x=0 and moved by transform, so it glides from point to point (attributes don't animate). */}
          <line x1={0} x2={0} y1={PAD.top} y2={PAD.top + plotH} stroke="var(--vt-line-strong)" className={glide ? "vt-glide" : undefined}
            style={{ transform: `translateX(${x(shown)}px)`, opacity: a ? 1 : 0 }} />
          <path d={path} fill="none" stroke="var(--vt-accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" pathLength={1} className="vt-draw" />
          {points.map((p, i) => {
            const lv = LEVEL[worst(p)];
            const href = `/review?id=${p.content_id}`;
            return (
              <a key={p.content_id} href={href} aria-label={`${p.title}, ${day(p.at)}: ${p.summary}`}
                onPointerDown={(e) => setTouch(e.pointerType !== "mouse")}
                onClick={(e) => {
                  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // a new tab or window, as any link
                  e.preventDefault();
                  if (touch && active !== i) { pick(i); return; }
                  router.push(href);
                }}
                onMouseEnter={() => pick(i)} onFocus={() => { pick(i); setFocused(i); }}
                onBlur={() => { pick(null); setFocused(null); }}
                className="cursor-pointer outline-none">
                <circle cx={x(i)} cy={y(p.distance)} r={hit} fill="transparent" />
                {focused === i && <circle cx={x(i)} cy={y(p.distance)} r={12} fill="none" stroke="var(--vt-accent)" strokeWidth={2} />}
                {p.drift.length > 0 && <circle cx={x(i)} cy={y(p.distance)} r={8.5} fill="none" stroke={lv.color} strokeWidth={1.5} />}
                <circle cx={x(i)} cy={y(p.distance)} r={active === i ? 6 : 4.5} fill={lv.color} stroke="var(--vt-raised)" strokeWidth={2}
                  className="transition-[r] duration-150" />
              </a>
            );
          })}
          {[0, points.length - 1].filter((i, n, all) => all.indexOf(i) === n).map((i) => (
            <text key={i} x={x(i)} y={H - 8} textAnchor={points.length === 1 ? "middle" : i ? "end" : "start"} className="fill-[var(--vt-subtle)] text-[11px]">
              {day(points[i].at)}
            </text>
          ))}
        </svg>
        {a && (
          <div role="tooltip" className={`vt-pop ${glide ? "vt-glide" : ""} pointer-events-none absolute z-10 w-[min(18rem,calc(100%-1rem))] rounded-xl border border-line bg-raised p-3 text-xs shadow-[var(--vt-shadow-pop)]`}
            // Placed by top or bottom, never by transform: the pop-in animation owns transform and would undo it.
            style={{
              left: Math.min(Math.max(0, x(active!) - 144), width - Math.min(288, width - 16)),
              ...(y(a.distance) > H / 2 ? { bottom: H - y(a.distance) + 14 } : { top: y(a.distance) + 14 }),
            }}>
            <p className="font-semibold text-ink">{a.title}</p>
            <p className="mt-0.5 text-subtle">{day(a.at)} · {channelName(a.channel)}{a.event ? ` · ${a.event}` : ""} · {STATUS_LABEL[a.status] ?? a.status}</p>
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
            <p className="mt-2 font-medium text-accent">
              {a.distance ? `${a.distance} from the brand` : "On the line"} · {touch ? "tap again" : "click"} to open
            </p>
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

"use client";

import { useState } from "react";

/**
 * Stacked daily bars that always fit their card. The charting library pages its
 * x-axis by width, which hid the most recent days on narrow screens. Bars are capped
 * in width so a short range doesn't turn into slabs, and segments are split by a 2px gap.
 *
 * Hover is one layer for the whole chart, not one tooltip per bar: the pointer's x picks the day, and
 * a highlight band and a single tooltip glide to it, so moving across the chart reads as one motion.
 */
export function TrendBars({ data, series }: {
  data: { label: string; values: number[] }[];
  series: { name: string; colour: string }[];
}) {
  const [active, setActive] = useState<number | null>(null);
  // The last day pointed at, so the tooltip fades out where it was instead of jumping home first.
  const [shown, setShown] = useState(0);
  const n = data.length;
  const totals = data.map((d) => d.values.reduce((a, b) => a + b, 0));
  const max = Math.max(1, ...totals);
  // One reference line at a round number near the top (9, 20, 300) gives the bars a scale without a grid.
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const ref = Math.floor(max / magnitude) * magnitude;
  const height = (i: number) => (totals[i] / max) * 92;

  function point(e: React.PointerEvent<HTMLDivElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.min(n - 1, Math.max(0, Math.floor(((e.clientX - box.left) / box.width) * n)));
    setActive(i);
    setShown(i);
  }

  const at = data[shown];
  // Near the edges the tooltip hangs inward, so it never spills out of the card.
  const shift = shown < n * 0.2 ? "0%" : shown >= n * 0.8 ? "-100%" : "-50%";
  return (
    <div className="flex h-full flex-col">
      <div className="relative min-h-0 flex-1 touch-pan-y" role="img"
        aria-label={`Daily findings: ${data.map((d, i) => `${d.label} ${totals[i]}`).join(", ")}`}
        onPointerMove={point} onPointerDown={point} onPointerLeave={() => setActive(null)}>
        <div aria-hidden className="absolute inset-x-0 border-t border-dashed border-line" style={{ bottom: `${(ref / max) * 92}%` }}>
          <span className="absolute -top-2.5 left-0 bg-surface pr-1.5 text-[11px] tabular-nums text-subtle">{ref}</span>
        </div>
        <div aria-hidden className="vt-glide absolute inset-y-0 left-0 rounded-md bg-sunken"
          style={{ width: `${100 / n}%`, transform: `translateX(${shown * 100}%)`, opacity: active == null ? 0 : 0.8 }} />
        <div className="absolute inset-0 flex items-end gap-1.5 border-b border-line-strong">
          {data.map((d, i) => (
            <div key={d.label} className="relative flex h-full min-w-0 flex-1 justify-center">
              <div className="vt-grow flex h-full w-full max-w-7 flex-col justify-end" style={{ "--vt-i": i } as React.CSSProperties}>
                <div className={`flex w-full flex-col-reverse gap-[2px] transition-opacity duration-200 ${
                  active == null || active === i ? "opacity-100" : "opacity-55"}`} style={{ height: `${height(i)}%` }}>
                  {d.values.map((v, k) => v > 0 && (
                    <div key={k} className="rounded-[2px] last:rounded-t-[4px]" style={{ flexGrow: v, background: series[k].colour }} />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
        {at && (
          <div aria-hidden className="vt-glide pointer-events-none absolute z-10 mb-2 whitespace-nowrap rounded-lg border border-line bg-raised px-2.5 py-1.5 text-xs shadow-[var(--vt-shadow-pop)]"
            style={{ left: `${((shown + 0.5) / n) * 100}%`, bottom: `${Math.min(height(shown), 70)}%`, transform: `translateX(${shift})`,
              opacity: active == null ? 0 : 1 }}>
            <p className="font-semibold">{at.label} · {totals[shown]} finding{totals[shown] === 1 ? "" : "s"}</p>
            {at.values.map((v, k) => v > 0 && (
              <p key={k} className="flex items-center gap-1.5 text-muted">
                <span className="h-2 w-2 rounded-full" style={{ background: series[k].colour }} />{series[k].name} {v}
              </p>
            ))}
          </div>
        )}
      </div>
      <div className="mt-1.5 flex gap-1.5">
        {data.map((d, i) => (
          <span key={d.label} className={`min-w-0 flex-1 truncate text-center text-[11px] tabular-nums transition-colors ${
            active === i ? "font-medium text-ink" : "text-subtle"}`}>
            {/* Every other day, counted back from today so the latest is always labelled; the pointed-at day always. */}
            {(n - 1 - i) % 2 === 0 || active === i ? d.label : ""}
          </span>
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {series.map((s) => (
          <li key={s.name} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2 w-2 rounded-full" style={{ background: s.colour }} />{s.name}
          </li>
        ))}
      </ul>
    </div>
  );
}

import Link from "next/link";
import { relativeTime } from "@/lib/review-client";
import type { CreatorRow } from "@/lib/types";

/** Busiest first: who has work waiting, then who writes the most. */
export function byWaiting(rows: CreatorRow[]): CreatorRow[] {
  return [...rows].sort((a, b) => (b.by_status.in_review ?? 0) - (a.by_status.in_review ?? 0) || b.pieces - a.pieces);
}

/**
 * The creator roster, used whole on /creators and trimmed on the dashboard. One table, so the two
 * never disagree about what a creator's numbers are.
 */
export function CreatorTable({ rows, compact = false }: { rows: CreatorRow[]; compact?: boolean }) {
  const cell = compact ? "py-2" : "py-3";
  return (
    // On a phone the full table drops to the compact columns (who, waiting, drift) instead of scrolling sideways.
    <table className={`w-full table-fixed text-sm ${compact ? "" : "sm:min-w-[40rem]"}`}>
      <colgroup>
        <col />
        {!compact && <><col className="hidden w-20 sm:table-column" /><col className="hidden w-24 sm:table-column" /></>}
        <col className="w-20" />
        {!compact && <col className="hidden w-20 sm:table-column" />}
        <col className={compact ? "w-32" : "w-32 sm:w-44"} />
      </colgroup>
      <thead>
        <tr className={`text-left text-[11px] font-medium uppercase tracking-wide text-subtle ${compact ? "" : "border-b border-line"}`}>
          <th scope="col" className={`font-medium ${compact ? "pb-2 pl-2" : "px-4 py-2.5"}`}>Creator</th>
          {!compact && <>
            <th scope="col" className="hidden px-2 py-2.5 text-right font-medium sm:table-cell">Pieces</th>
            <th scope="col" className="hidden px-2 py-2.5 text-right font-medium sm:table-cell" title="Pieces with nothing to fix when first sent">On brand</th>
          </>}
          <th scope="col" className={`text-right font-medium ${compact ? "pb-2" : "px-2 py-2.5"}`}>Waiting</th>
          {!compact && <th scope="col" className="hidden px-2 py-2.5 text-right font-medium sm:table-cell">Asked</th>}
          <th scope="col" className={`text-right font-medium ${compact ? "pb-2 pr-2" : "px-4 py-2.5"}`} title="Distance from the brand, piece by piece">Drift</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {rows.map((c) => {
          const back = c.by_status.changes_requested ?? 0;
          return (
            // The whole row opens the creator: the name's link stretches over it (after:inset-0), so it
            // stays one real link for keyboards and screen readers rather than a clickable row.
            <tr key={c.id} className="group relative transition-colors hover:bg-sunken/60">
              <td className={`truncate ${cell} ${compact ? "pl-2" : "px-4"}`}>
                <Link href={`/creators?id=${c.id}`}
                  className="font-medium after:absolute after:inset-0 after:content-[''] group-hover:text-accent focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:-outline-offset-2 focus-visible:after:outline-[var(--vt-accent)] focus-visible:after:outline">{c.name}</Link>
                <span className="block truncate text-[11px] text-subtle">
                  {back ? <span className="text-[var(--vt-warning)]">{back} sent back · </span> : null}
                  {c.last_at ? `active ${relativeTime(c.last_at)}` : c.above_clearance ? "above your clearance" : "nothing yet"}
                </span>
              </td>
              {!compact && <>
                <td className={`${cell} hidden px-2 text-right tabular-nums sm:table-cell`}>{c.pieces}</td>
                <td className={`${cell} hidden px-2 text-right tabular-nums text-muted sm:table-cell`}>
                  {c.reviewed ? <>{c.on_brand_as_sent}<span className="text-subtle"> / {c.reviewed}</span></> : <span className="text-subtle">-</span>}
                </td>
              </>}
              <td className={`${cell} text-right tabular-nums ${compact ? "" : "px-2"}`}>{c.by_status.in_review || <span className="text-subtle">0</span>}</td>
              {!compact && (
                <td className={`${cell} hidden px-2 text-right tabular-nums sm:table-cell ${c.open_escalations ? "font-semibold text-accent" : "text-subtle"}`}>{c.open_escalations}</td>
              )}
              <td className={`${cell} ${compact ? "pr-2" : "px-4"}`}>
                <span className="flex items-center justify-end gap-2.5">
                  <Sparkline values={c.recent} />
                  <span className="w-8 text-right text-xs tabular-nums text-muted" title="Average distance from the brand">
                    {c.average_distance == null ? "-" : Math.round(c.average_distance)}
                  </span>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/**
 * The creator's last pieces as a tiny line on a fixed 0 to 100 scale, so lines compare across rows:
 * flat along the bottom is on brand. The last point is marked in its level's colour.
 */
export function Sparkline({ values, width = 72, height = 22 }: { values: number[]; width?: number; height?: number }) {
  if (values.length === 0) return <span aria-hidden className="text-xs text-subtle" style={{ width }}>-</span>;
  const pad = 3;
  const x = (i: number) => values.length === 1 ? width / 2 : pad + (i * (width - 2 * pad)) / (values.length - 1);
  const y = (v: number) => height - pad - (Math.min(100, v) / 100) * (height - 2 * pad);
  const last = values.at(-1)!;
  const tone = last >= 40 ? "var(--vt-blocker)" : last >= 15 ? "var(--vt-warning)" : last > 0 ? "var(--vt-advisory)" : "var(--vt-ok)";
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" className="shrink-0 overflow-visible"
      aria-label={`Last ${values.length} pieces, distance from the brand: ${values.join(", ")}`}>
      <line x1={pad} x2={width - pad} y1={height - pad} y2={height - pad} stroke="var(--vt-line)" strokeWidth="1" />
      {values.length > 1 && (
        <polyline points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")} fill="none" stroke="var(--vt-accent)"
          strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" pathLength={1} className="vt-draw" />
      )}
      <circle cx={x(values.length - 1)} cy={y(last)} r="2.75" fill={tone} stroke="var(--vt-surface)" strokeWidth="1.5" />
    </svg>
  );
}

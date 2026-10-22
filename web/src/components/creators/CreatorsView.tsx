"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError, creatorTrack, listCreators, relativeTime } from "@/lib/review-client";
import type { CreatorRow, CreatorTrack } from "@/lib/types";
import { ChevronIcon } from "../Icons";
import { Panel } from "../ui";
import { DriftChart } from "./DriftChart";

const CATEGORY: Record<string, string> = {
  claims: "Claims", tone: "Tone", terminology: "Terminology", messaging: "Messaging", visual: "Visuals",
  accessibility: "Accessibility", legal: "Legal", confidentiality: "Confidentiality",
};
const STATUS: Record<string, string> = {
  draft: "Draft", in_review: "Waiting", changes_requested: "Sent back", approved: "Approved", published: "Published",
  withdrawn: "Withdrawn",
};

/** /creators lists everyone writing for the brand; /creators?id= is one person's record and line. */
export function CreatorsView() {
  const id = Number(useSearchParams().get("id")) || null;
  return id ? <Profile id={id} key={id} /> : <Roster />;
}

function Failure({ err }: { err: Error }) {
  const offline = err instanceof ApiError && err.status === 503;
  return <p className="rounded-xl bg-sunken px-4 py-6 text-center text-sm text-muted">
    {offline ? "This needs the Verytas API." : `Couldn't load this: ${err.message}`}
  </p>;
}

function Roster() {
  const [rows, setRows] = useState<CreatorRow[] | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => { listCreators().then(setRows).catch(setErr); }, []);
  if (err) return <Failure err={err} />;
  if (!rows) return <div className="h-64 animate-pulse rounded-[14px] bg-sunken" aria-busy="true" aria-label="Loading" />;
  if (!rows.length) return <p className="rounded-xl bg-sunken px-4 py-6 text-center text-sm text-muted">No creators yet.</p>;
  const sorted = [...rows].sort((a, b) => (b.by_status.in_review ?? 0) - (a.by_status.in_review ?? 0) || b.pieces - a.pieces);
  return (
    <div className="vt-card overflow-x-auto">
      <table className="w-full min-w-[34rem] table-fixed text-sm">
        <colgroup><col /><col className="w-20" /><col className="w-20" /><col className="w-24" /><col className="w-24" /><col className="w-28" /></colgroup>
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-medium uppercase tracking-wide text-subtle">
            <th scope="col" className="px-4 py-2.5 font-medium">Creator</th>
            <th scope="col" className="px-2 py-2.5 text-right font-medium">Pieces</th>
            <th scope="col" className="px-2 py-2.5 text-right font-medium">Waiting</th>
            <th scope="col" className="px-2 py-2.5 text-right font-medium">Sent back</th>
            <th scope="col" className="px-2 py-2.5 text-right font-medium">Asked</th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">Active</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {sorted.map((c) => (
            <tr key={c.id} className="transition-colors hover:bg-sunken/60">
              <td className="truncate px-4 py-3">
                <Link href={`/creators?id=${c.id}`} className="font-medium hover:text-accent">{c.name}</Link>
              </td>
              <td className="px-2 py-3 text-right tabular-nums">{c.pieces}</td>
              <td className="px-2 py-3 text-right tabular-nums">{c.by_status.in_review || <span className="text-subtle">0</span>}</td>
              <td className="px-2 py-3 text-right tabular-nums">{c.by_status.changes_requested || <span className="text-subtle">0</span>}</td>
              <td className={`px-2 py-3 text-right tabular-nums ${c.open_escalations ? "font-semibold text-accent" : "text-subtle"}`}>{c.open_escalations}</td>
              <td className="px-4 py-3 text-right text-muted">
                {c.last_at ? relativeTime(c.last_at) : c.above_clearance ? "above your clearance" : "never"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Profile({ id }: { id: number }) {
  const [track, setTrack] = useState<CreatorTrack | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => { creatorTrack(id).then(setTrack).catch(setErr); }, [id]);

  const back = (
    <Link href="/creators" className="inline-flex items-center gap-1 text-xs font-medium text-subtle hover:text-ink">
      <ChevronIcon size={13} className="rotate-90" /> All creators
    </Link>
  );
  if (err) return <div className="flex flex-col gap-4">{back}<Failure err={err} /></div>;
  if (!track) return <div className="flex flex-col gap-4">{back}<div className="h-80 animate-pulse rounded-[14px] bg-sunken" aria-busy="true" aria-label="Loading" /></div>;

  const { person, stats, points, categories } = track;
  const recent = [...points].reverse();
  const top = Object.entries(categories).slice(0, 4);
  const tiles = [
    { label: "On brand as sent", value: stats.reviewed ? `${stats.on_brand_as_sent} of ${stats.reviewed}` : "None yet" },
    { label: "Average distance", value: stats.average_distance == null ? "n/a" : String(stats.average_distance) },
    { label: "Sent back now", value: String(stats.changes_requested) },
    { label: "Asked the brand team", value: String(stats.open_escalations) },
  ];
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-2">
          {back}
          <h2 className="text-xl font-semibold tracking-tight">{person.name}</h2>
        </div>
        <Link href={`/review?queue=all&creator=${person.id}`} className="vt-btn vt-btn-quiet py-1.5 text-xs">Their pieces in the queue</Link>
      </div>

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t) => (
          <div key={t.label} className="vt-card px-4 py-3">
            <dt className="text-xs text-muted">{t.label}</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">{t.value}</dd>
          </div>
        ))}
      </dl>

      <Panel title="Distance from the brand, piece by piece">
        <p className="-mt-2 mb-3 text-xs text-muted">Flat along zero means every piece arrived on brand. Hover a point for why; click to open it.</p>
        <DriftChart points={points} />
        {stats.above_clearance > 0 && (
          <p className="mt-3 text-xs text-muted">
            {stats.above_clearance} more {stats.above_clearance === 1 ? "piece is" : "pieces are"} above your clearance and not
            shown, so this line is not their whole record.
          </p>
        )}
        {top.length > 0 && (
          <p className="mt-3 text-xs text-muted">
            Most often: {top.map(([c, n]) => `${CATEGORY[c] ?? c} ${n}`).join(" · ")}
          </p>
        )}
      </Panel>

      <Panel title="Pieces, newest first">
        {recent.length === 0 ? <p className="text-sm text-muted">Nothing reviewed yet.</p> : (
          <ul className="-my-2 divide-y divide-line">
            {recent.map((p) => (
              <li key={p.content_id}>
                <Link href={`/review?id=${p.content_id}`} className="group flex items-start gap-3 py-2.5">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${p.blockers ? "bg-[var(--vt-blocker)]" : p.warnings
                    ? "bg-[var(--vt-warning)]" : p.advisories ? "bg-[var(--vt-advisory)]" : "bg-[var(--vt-ok)]"}`} aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium group-hover:text-accent">{p.title}</span>
                    <span className="block text-xs text-muted">{p.summary}</span>
                  </span>
                  <span className="shrink-0 text-right text-xs">
                    <span className="block text-muted">{STATUS[p.status] ?? p.status}</span>
                    <span className="block tabular-nums text-subtle">{relativeTime(p.at)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

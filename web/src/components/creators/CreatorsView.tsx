"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { useOnRefresh } from "@/lib/refresh";
import { ApiError, creatorTrack, listCreators, relativeTime } from "@/lib/review-client";
import type { CreatorRow, CreatorTrack } from "@/lib/types";
import { BackButton } from "../BackButton";
import { Panel } from "../ui";
import { byWaiting, CreatorTable } from "./CreatorTable";
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
  const load = useCallback(() => { listCreators().then((r) => { setRows(r); setErr(null); }).catch(setErr); }, []);
  useEffect(() => { load(); }, [load]);
  useOnRefresh(load);
  if (err) return <Failure err={err} />;
  if (!rows) return <div className="h-64 animate-pulse rounded-[14px] bg-sunken" aria-busy="true" aria-label="Loading" />;
  if (!rows.length) return <p className="rounded-xl bg-sunken px-4 py-6 text-center text-sm text-muted">No creators yet.</p>;
  return <div className="vt-card overflow-x-auto"><CreatorTable rows={byWaiting(rows)} /></div>;
}

function Profile({ id }: { id: number }) {
  const [track, setTrack] = useState<CreatorTrack | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const load = useCallback(() => { creatorTrack(id).then((t) => { setTrack(t); setErr(null); }).catch(setErr); }, [id]);
  useEffect(() => { load(); }, [load]);
  useOnRefresh(load);

  const back = <BackButton href="/creators" label="All creators" />;
  if (err) return <div className="flex flex-col gap-4">{back}<Failure err={err} /></div>;
  if (!track) return <div className="flex flex-col gap-4">{back}<div className="h-80 animate-pulse rounded-[14px] bg-sunken" aria-busy="true" aria-label="Loading" /></div>;

  const { person, stats, points, categories } = track;
  const recent = [...points].reverse();
  const top = Object.entries(categories).slice(0, 4);
  const tiles = [
    { label: "On brand as sent", value: stats.reviewed ? `${stats.on_brand_as_sent} of ${stats.reviewed}` : "None yet" },
    { label: "Average distance (0 is on brand)", value: stats.average_distance == null ? "n/a" : `${stats.average_distance} / 100` },
    { label: "Sent back now", value: String(stats.changes_requested) },
    { label: "Asked the brand team", value: String(stats.open_escalations) },
  ];
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        {back}
        <h2 className="text-xl font-semibold tracking-tight">{person.name}</h2>
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

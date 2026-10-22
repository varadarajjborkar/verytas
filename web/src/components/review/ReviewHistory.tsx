"use client";

import { useMemo, useState } from "react";
import { FINISHED, relativeTime, STATUS_LABEL } from "@/lib/review-client";
import type { ContentRow } from "@/lib/types";
import { PlusIcon } from "../Icons";

/** Every review the person can open, newest activity first. Finished pieces stay listed, struck through. */
export function ReviewHistory({ rows, loading, selected, mine, demo, onMine, onSelect, onNew }: {
  rows: ContentRow[];
  loading: boolean;
  selected: number | null;
  mine: boolean;
  demo: boolean;
  onMine: (mine: boolean) => void;
  onSelect: (id: number) => void;
  onNew: () => void;
}) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? rows.filter((r) => r.title.toLowerCase().includes(q) || r.channel.toLowerCase().includes(q)) : rows;
  }, [rows, query]);

  return (
    <nav aria-label="Reviews" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-3 p-3">
        <button type="button" onClick={onNew} aria-current={selected == null ? "page" : undefined}
          className="vt-btn vt-btn-primary w-full">
          <PlusIcon size={15} /> New review
        </button>
        <div role="radiogroup" aria-label="Whose reviews" className="grid grid-cols-2 gap-1 rounded-lg bg-sunken p-0.5 text-xs font-medium">
          {[{ v: true, l: "Mine" }, { v: false, l: "Everyone" }].map(({ v, l }) => (
            <button key={l} type="button" role="radio" aria-checked={mine === v} onClick={() => onMine(v)}
              className={`rounded-md py-1.5 transition ${mine === v ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
              {l}
            </button>
          ))}
        </div>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search reviews" aria-label="Search reviews"
          className="vt-input py-1.5 text-[13px]" />
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {demo && <li className="px-2 py-2 text-xs text-muted">Demo mode: history needs the Verytas API.</li>}
        {!demo && loading && rows.length === 0 && [0, 1, 2, 3].map((i) => (
          <li key={i} className="mx-1 my-1.5 h-12 animate-pulse rounded-lg bg-sunken" />
        ))}
        {!demo && !loading && shown.length === 0 && (
          <li className="px-2 py-2 text-xs text-muted">{query ? "No review matches that search." : "No reviews yet."}</li>
        )}
        {shown.map((r) => {
          const finished = FINISHED.includes(r.status);
          const lr = r.latest_review;
          const running = lr && (lr.status === "queued" || lr.status === "running");
          return (
            <li key={r.id}>
              <button type="button" onClick={() => onSelect(r.id)} aria-current={r.id === selected ? "page" : undefined}
                className={`group flex w-full flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left transition ${
                  r.id === selected ? "bg-accent/12" : "hover:bg-sunken"}`}>
                <span className="flex items-center gap-2">
                  <span className={`min-w-0 flex-1 truncate text-sm ${finished ? "text-subtle line-through decoration-1" : "font-medium"}`}>
                    {r.title}
                  </span>
                  {running ? (
                    <span aria-label="Checking" className="h-3 w-3 shrink-0 animate-spin rounded-full border-[1.5px] border-accent border-t-transparent" />
                  ) : !finished && lr && lr.blockers > 0 ? (
                    <span title={`${lr.blockers} blocker${lr.blockers === 1 ? "" : "s"}`}
                      className="shrink-0 rounded-full bg-[var(--vt-blocker-bg)] px-1.5 text-[11px] font-semibold tabular-nums text-[var(--vt-blocker)]">
                      {lr.blockers}
                    </span>
                  ) : null}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-subtle">
                  <span className="truncate capitalize">{r.channel.replace("_", " ")}</span>
                  <span aria-hidden>·</span>
                  <span className="shrink-0">{STATUS_LABEL[r.status]}</span>
                  <span className="ml-auto shrink-0">{relativeTime(r.updated_at)}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

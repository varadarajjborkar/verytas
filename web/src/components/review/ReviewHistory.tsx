"use client";

import { type KeyboardEvent, useMemo, useState } from "react";
import { FINISHED, relativeTime, STATUS_HINT, STATUS_LABEL } from "@/lib/review-client";
import type { ContentRow } from "@/lib/types";
import { DashboardIcon, PanelIcon, PlusIcon } from "../Icons";
import { channelName } from "@/lib/channels";
import { SearchField } from "../SearchField";

// What GET /contents returns by default; past this the list says it is partial.
const LIST_CAP = 200;

export type Scope = { key: string; label: string; count?: number };

/**
 * Every review the person can open, newest activity first. Finished pieces stay listed, struck through.
 * Creators see their own pieces; the brand team gets scopes (waiting, with creator, ...) instead,
 * and a queue overview in place of the new-review button.
 */
export function ReviewHistory({ rows, loading, selected, scopes, scope, demo, onScope, onSelect, onNew, onCollapse,
  homeLabel, fresh }: {
  rows: ContentRow[];
  loading: boolean;
  selected: number | null;
  scopes: Scope[];
  scope: string;
  demo: boolean;
  onScope: (key: string) => void;
  onSelect: (id: number) => void;
  onNew: () => void;
  onCollapse?: () => void;
  /** The button that leaves an open review: "New review" for creators, "Queue overview" for the brand team. */
  homeLabel: { text: string; icon: "plus" | "queue" };
  /** Pieces with news from the brand team the creator hasn't opened yet. */
  fresh?: Set<number>;
}) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? rows.filter((r) => r.title.toLowerCase().includes(q) || r.channel.toLowerCase().includes(q)) : rows;
  }, [rows, query]);

  // Radio keys: arrows move the choice, and only the checked option is a tab stop.
  const onRadioKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[e.key];
    if (!step) return;
    e.preventDefault();
    const at = scopes.findIndex((x) => x.key === scope);
    onScope(scopes[(at + step + scopes.length) % scopes.length].key);
    requestAnimationFrame(() => e.currentTarget?.querySelector<HTMLElement>("[aria-checked='true']")?.focus());
  };

  return (
    <nav aria-label="Reviews" className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-3 p-3">
        <div className="flex items-center gap-1.5">
          <button type="button" onClick={onNew} aria-current={selected == null ? "page" : undefined}
            className={`vt-btn flex-1 ${homeLabel.icon === "plus" ? "vt-btn-primary" : "vt-btn-quiet"}`}>
            {homeLabel.icon === "plus" ? <PlusIcon size={15} /> : <DashboardIcon size={15} />} {homeLabel.text}
          </button>
          {onCollapse && (
            <button type="button" onClick={onCollapse} aria-label="Collapse reviews" title="Collapse reviews"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
              <PanelIcon size={16} />
            </button>
          )}
        </div>
        {scopes.length > 1 && (
          <div role="radiogroup" aria-label="Which pieces" onKeyDown={onRadioKey}
            className="grid grid-cols-2 gap-1 rounded-lg bg-sunken p-0.5 text-xs font-medium">
            {scopes.map(({ key, label, count }) => (
              <button key={key} type="button" role="radio" aria-checked={scope === key} tabIndex={scope === key ? 0 : -1}
                onClick={() => onScope(key)}
                className={`flex items-center justify-center gap-1.5 rounded-md py-1.5 transition ${
                  scope === key ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
                {label}
                {count != null && <span className="tabular-nums text-subtle">{count}</span>}
              </button>
            ))}
          </div>
        )}
        <SearchField value={query} onChange={setQuery} placeholder="Search reviews" label="Search reviews" />
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {demo && <li className="px-2 py-2 text-xs text-muted">Demo mode: history needs the Verytas API.</li>}
        {!demo && loading && rows.length === 0 && [0, 1, 2, 3].map((i) => (
          <li key={i} className="mx-1 my-1.5 h-12 animate-pulse rounded-lg bg-sunken" />
        ))}
        {!demo && !loading && shown.length === 0 && (
          <li className="px-2 py-2 text-xs text-muted">{query ? "No review matches that search."
            : scopes.length > 1 ? "No pieces in this group yet. Try another one above." : "No pieces yet. They show here once one is started."}</li>
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
                  {fresh?.has(r.id) && r.id !== selected && (
                    <span role="img" aria-label="New from the brand team" title="New from the brand team"
                      className="h-2 w-2 shrink-0 rounded-full bg-accent" />
                  )}
                  <span className={`min-w-0 flex-1 truncate text-sm ${finished ? "text-subtle line-through decoration-1" : "font-medium"}`}>
                    {r.title}
                  </span>
                  {running ? (
                    <span role="img" aria-label="Checking" className="h-3 w-3 shrink-0 animate-spin rounded-full border-[1.5px] border-accent border-t-transparent" />
                  ) : !finished && lr && lr.blockers > 0 ? (
                    <span title={`${lr.blockers} blocker${lr.blockers === 1 ? "" : "s"}`} role="img" aria-label={`${lr.blockers} must fix`}
                      className="shrink-0 rounded-full bg-[var(--vt-blocker-bg)] px-1.5 text-[11px] font-semibold tabular-nums text-[var(--vt-blocker)]">
                      {lr.blockers}
                    </span>
                  ) : null}
                </span>
                <span className="flex items-center gap-1.5 text-[11px] text-subtle">
                  <span className="truncate">{channelName(r.channel)}</span>
                  <span aria-hidden>·</span>
                  <span className="shrink-0" title={STATUS_HINT[r.status]}>{STATUS_LABEL[r.status]}</span>
                  <span className="ml-auto shrink-0">{relativeTime(r.updated_at)}</span>
                </span>
              </button>
            </li>
          );
        })}
        {rows.length >= LIST_CAP && (
          <li className="px-2 py-2 text-[11px] text-subtle">Showing the {LIST_CAP} most recent. Search narrows within these.</li>
        )}
      </ul>
    </nav>
  );
}

"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  GROUPS, type Group, isQueue, isSort, priority, priorityBand, QUEUE_ORDER, QUEUES, type Queue, type Signal, SIGNALS,
  sinceOf, type Sort, SORTS, sortRows,
} from "@/lib/queue";
import { ApiError, listContents, listEvents, listPeople, relativeTime, STATUS_LABEL } from "@/lib/review-client";
import type { BrandEvent, ContentRow, Person } from "@/lib/types";
import { ArrowRightIcon, ChevronIcon, CloseIcon, InboxIcon, RefreshIcon } from "../Icons";
import { StageDots } from "../Journey";
import { useViewer } from "../Viewer";
import { ReviewView } from "./ReviewView";

const STAGE_ORDER: ContentRow["status"][] = ["in_review", "changes_requested", "draft", "approved", "published", "withdrawn"];

/**
 * The brand team's review queue, full width: every creator's pieces, split by
 * where they are, ranked by urgency, and filterable by creator, channel, event
 * and signal. Opening a piece keeps the queue's order, so the reviewer can step
 * through it with previous and next. All of it lives in the URL.
 */
export function ReviewQueue() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { me } = useViewer();
  const [rows, setRows] = useState<ContentRow[] | null>(null);
  const [people, setPeople] = useState<Map<number, Person>>(new Map());
  const [events, setEvents] = useState<BrandEvent[]>([]);
  const [demo, setDemo] = useState(false);
  const seq = useRef(0);

  const get = (k: string) => params.get(k);
  const queue: Queue = isQueue(get("queue")) ? get("queue") as Queue : "waiting";
  const sort: Sort = isSort(get("sort")) ? get("sort") as Sort : queue === "waiting" || queue === "escalated" ? "priority" : "recent";
  const group = (get("group") && Object.hasOwn(GROUPS, get("group")!) ? get("group") : "none") as Group;
  const creator = get("creator") ?? "all";
  const channel = get("channel") ?? "all";
  const event = get("event") ?? "all";
  const signal = (get("signal") && Object.hasOwn(SIGNALS, get("signal")!) ? get("signal") : null) as Signal | null;
  const query = get("q") ?? "";
  const selected = Number(get("id")) || null;

  const set = useCallback((patch: Record<string, string | number | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v == null || v === "" || v === "all" || v === "none") next.delete(k);
      else next.set(k, String(v));
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  const refresh = useCallback(() => {
    const ticket = ++seq.current;
    return listContents(false).then((r) => { if (ticket === seq.current) setRows(r); }).catch((err) => {
      if (err instanceof ApiError && err.status === 503) setDemo(true);
      setRows([]);
    });
  }, []);
  useEffect(() => {
    void refresh();
    listPeople().then((ps) => setPeople(new Map(ps.map((p) => [p.id, p])))).catch(() => {});
    listEvents().then(setEvents).catch(() => {});
  }, [refresh]);
  // Reviews still running keep the list fresh, one request at a time, and none in a background tab.
  const pending = (rows ?? []).some((r) => r.latest_review && (r.latest_review.status === "queued" || r.latest_review.status === "running"));
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(() => { if (!document.hidden) void refresh(); }, 5000);
    return () => clearInterval(t);
  }, [pending, refresh]);

  const nameOf = useCallback((id: number) => people.get(id)?.name ?? "Unknown", [people]);
  const eventName = useMemo(() => new Map(events.map((e) => [e.id, e.name])), [events]);
  const all = useMemo(() => rows ?? [], [rows]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sortRows(all.filter((r) => QUEUES[queue].test(r)
      && (creator === "all" || String(r.created_by) === creator)
      && (channel === "all" || r.channel === channel)
      && (event === "all" || (event === "none" ? r.event_id == null : String(r.event_id) === event))
      && (!signal || SIGNALS[signal].test(r))
      && (!q || r.title.toLowerCase().includes(q) || nameOf(r.created_by).toLowerCase().includes(q))), sort, nameOf);
  }, [all, queue, creator, channel, event, signal, query, sort, nameOf]);

  const creators = useMemo(() => [...new Set(all.map((r) => r.created_by))].map((id) => ({ id, name: nameOf(id) }))
    .sort((a, b) => a.name.localeCompare(b.name)), [all, nameOf]);
  const channels = useMemo(() => [...new Set(all.map((r) => r.channel))].sort(), [all]);
  const filters = [creator !== "all", channel !== "all", event !== "all", signal != null, query !== ""].filter(Boolean).length;

  if (selected != null && !demo) {
    const at = filtered.findIndex((r) => r.id === selected);
    const prev = at > 0 ? filtered[at - 1] : null;
    const next = at >= 0 && at < filtered.length - 1 ? filtered[at + 1] : null;
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => set({ id: null })} className="vt-btn vt-btn-quiet py-1.5">
            <ChevronIcon size={14} className="rotate-90" /> {QUEUES[queue].label}
          </button>
          {at >= 0 && <span className="text-xs tabular-nums text-subtle">{at + 1} of {filtered.length}</span>}
          <div className="ml-auto flex gap-1.5">
            <button type="button" disabled={!prev} onClick={() => prev && set({ id: prev.id })} className="vt-btn vt-btn-quiet py-1.5"
              aria-label="Previous piece in the queue">Previous</button>
            <button type="button" disabled={!next} onClick={() => next && set({ id: next.id })} className="vt-btn vt-btn-quiet py-1.5"
              aria-label="Next piece in the queue">Next <ArrowRightIcon size={14} /></button>
          </div>
        </div>
        <ReviewView key={selected} contentId={selected} role={me?.role ?? "reviewer"} userId={me?.id ?? null} onChanged={refresh} />
      </div>
    );
  }

  const groups = groupRows(filtered, group, nameOf, eventName);
  const counts = Object.fromEntries(QUEUE_ORDER.map((q) => [q, all.filter((r) => QUEUES[q].test(r)).length])) as Record<Queue, number>;
  const mustFix = filtered.reduce((n, r) => n + (r.latest_review?.blockers ?? 0), 0);
  const oldest = queue === "waiting" ? [...filtered].sort((a, b) => sinceOf(a).localeCompare(sinceOf(b)))[0] : undefined;

  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Queue" className="flex gap-1 overflow-x-auto border-b border-line">
        {QUEUE_ORDER.map((q) => (
          <button key={q} type="button" role="tab" aria-selected={queue === q} onClick={() => set({ queue: q === "waiting" ? null : q, sort: null })}
            className={`-mb-px flex shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              queue === q ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}>
            {q === "escalated" && <InboxIcon size={14} />}{QUEUES[q].label}
            <span className={`rounded-full px-1.5 text-[11px] tabular-nums ${queue === q ? "bg-accent/12 text-accent" : "bg-sunken text-subtle"}`}>
              {rows ? counts[q] : "·"}
            </span>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input value={query} onChange={(e) => set({ q: e.target.value })} placeholder="Search pieces or creators" aria-label="Search"
          className="vt-input w-56 py-1.5 text-xs" />
        <select value={creator} onChange={(e) => set({ creator: e.target.value })} aria-label="Creator" className="vt-input w-auto py-1.5 text-xs">
          <option value="all">Every creator</option>
          {creators.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={channel} onChange={(e) => set({ channel: e.target.value })} aria-label="Channel" className="vt-input w-auto py-1.5 text-xs capitalize">
          <option value="all">Every channel</option>
          {channels.map((c) => <option key={c} value={c}>{c.replace("_", " ")}</option>)}
        </select>
        <select value={event} onChange={(e) => set({ event: e.target.value })} aria-label="Event" className="vt-input w-auto py-1.5 text-xs">
          <option value="all">Any event</option>
          <option value="none">Not for an event</option>
          {events.map((e) => <option key={e.id} value={e.id}>{e.name}{e.live ? " (running)" : e.status === "cancelled" ? " (cancelled)" : ""}</option>)}
        </select>
        <select value={signal ?? "all"} onChange={(e) => set({ signal: e.target.value })} aria-label="Signal" className="vt-input w-auto py-1.5 text-xs">
          <option value="all">Any signal</option>
          {(Object.keys(SIGNALS) as Signal[]).map((k) => <option key={k} value={k}>{SIGNALS[k].label}</option>)}
        </select>
        <span className="mx-1 hidden h-5 w-px bg-line md:block" aria-hidden />
        <select value={sort} onChange={(e) => set({ sort: e.target.value })} aria-label="Sort" className="vt-input w-auto py-1.5 text-xs">
          {(Object.keys(SORTS) as Sort[]).map((k) => <option key={k} value={k}>Sort: {SORTS[k]}</option>)}
        </select>
        <select value={group} onChange={(e) => set({ group: e.target.value })} aria-label="Group" className="vt-input w-auto py-1.5 text-xs">
          {(Object.keys(GROUPS) as Group[]).map((k) => <option key={k} value={k}>{GROUPS[k]}</option>)}
        </select>
        {filters > 0 && (
          <button type="button" onClick={() => set({ creator: null, channel: null, event: null, signal: null, q: null })}
            className="flex items-center gap-1 text-xs font-medium text-muted hover:text-ink">
            <CloseIcon size={13} /> Clear {filters} filter{filters === 1 ? "" : "s"}
          </button>
        )}
      </div>

      <section className="vt-card min-w-0 overflow-hidden" aria-label={QUEUES[queue].title}>
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line px-4 py-3 md:px-5">
          <h2 className="text-sm font-semibold">{QUEUES[queue].title}</h2>
          <p className="text-xs text-muted">{QUEUES[queue].lead}</p>
          {rows && (
            <p className="ml-auto text-xs tabular-nums text-subtle">
              {filtered.length} piece{filtered.length === 1 ? "" : "s"}{mustFix ? ` · ${mustFix} must-fix` : ""}
              {oldest ? ` · oldest sent ${relativeTime(sinceOf(oldest))}` : ""}
            </p>
          )}
        </div>
        {demo ? (
          <p className="px-5 py-10 text-center text-sm text-muted">The queue needs the Verytas API. Connect it to see every creator&apos;s pieces.</p>
        ) : rows === null ? (
          <ul className="flex flex-col gap-2 p-4">{[0, 1, 2, 3, 4].map((i) => <li key={i} className="h-12 animate-pulse rounded-lg bg-sunken" />)}</ul>
        ) : filtered.length === 0 ? (
          <div className="px-5 py-10 text-center">
            <p className="text-sm font-medium">{filters ? "Nothing matches these filters" : queue === "waiting" ? "The queue is clear" : "Nothing here"}</p>
            <p className="mt-1 text-sm text-muted">
              {filters ? "Clear a filter to widen the list." : queue === "waiting" ? "Pieces appear here when creators send them for approval." : "Try another stage."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[52rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-medium uppercase tracking-wide text-subtle">
                  <th scope="col" className="w-20 py-2 pl-4 pr-2 font-medium md:pl-5">Priority</th>
                  <th scope="col" className="px-3 py-2 font-medium">Piece</th>
                  <th scope="col" className="px-3 py-2 font-medium">Where it is</th>
                  <th scope="col" className="px-3 py-2 font-medium">Latest check</th>
                  <th scope="col" className="px-3 py-2 font-medium">Signals</th>
                  <th scope="col" className="px-3 py-2 font-medium">{queue === "waiting" ? "Waiting" : "Updated"}</th>
                  <th scope="col" className="w-8 py-2 pr-4 md:pr-5"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              {groups.map(([label, items]) => (
                <tbody key={label} className="divide-y divide-line border-b border-line last:border-0">
                  {group !== "none" && (
                    <tr className="bg-sunken/50">
                      <th colSpan={7} scope="colgroup" className="px-4 py-1.5 text-left text-xs font-semibold md:px-5">
                        {label} <span className="font-normal tabular-nums text-subtle">{items.length}</span>
                      </th>
                    </tr>
                  )}
                  {items.map((r) => <QueueRow key={r.id} r={r} queue={queue} creatorName={nameOf(r.created_by)}
                    eventName={r.event_id ? eventName.get(r.event_id) : undefined} onOpen={() => set({ id: r.id })} />)}
                </tbody>
              ))}
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function QueueRow({ r, queue, creatorName, eventName, onOpen }: {
  r: ContentRow; queue: Queue; creatorName: string; eventName?: string; onOpen: () => void;
}) {
  const lr = r.latest_review;
  const band = priorityBand(priority(r));
  const initials = creatorName.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  return (
    <tr onClick={onOpen} className="group cursor-pointer transition-colors hover:bg-sunken/60">
      <td className="py-2.5 pl-4 pr-2 md:pl-5">
        {band ? (
          <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${band === "high" ? "text-[var(--vt-blocker)]" : band === "medium" ? "text-[var(--vt-warning)]" : "text-muted"}`}>
            <span aria-hidden className="flex gap-0.5">
              {[0, 1, 2].map((i) => (
                <span key={i} className={`h-2.5 w-1 rounded-sm ${i < (band === "high" ? 3 : band === "medium" ? 2 : 1) ? "bg-current" : "bg-line-strong"}`} />
              ))}
            </span>
            <span className="capitalize">{band}</span>
          </span>
        ) : <span className="text-xs text-subtle">-</span>}
      </td>
      <td className="max-w-0 px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-sunken text-[10px] font-semibold text-muted">{initials}</span>
          <div className="min-w-0">
            <button type="button" onClick={(e) => { e.stopPropagation(); onOpen(); }}
              className="block max-w-full truncate text-left font-medium hover:text-accent">{r.title}</button>
            <p className="truncate text-[11px] text-subtle">
              {creatorName} · <span className="capitalize">{r.channel.replace("_", " ")}</span>{r.version_count > 1 ? ` · v${r.version_count}` : ""}
              {eventName ? <> · <span className="text-accent">{eventName}</span></> : null}
            </p>
          </div>
        </div>
      </td>
      <td className="whitespace-nowrap px-3 py-2.5">
        <span className="flex items-center gap-2.5">
          <StageDots status={r.status} checked={lr?.status === "done"} />
          <span className="text-xs text-muted">{STATUS_LABEL[r.status]}</span>
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-xs">
        {!lr ? <span className="text-subtle">Not checked</span>
          : lr.status === "failed" ? <span className="text-[var(--vt-warning)]">Check failed</span>
            : lr.status !== "done" ? <span className="flex items-center gap-1.5 text-subtle"><span className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-accent border-t-transparent" />Checking</span>
              : (
                <span className="flex items-center gap-2">
                  {lr.overall != null && <span className="w-9 tabular-nums">{Math.round(lr.overall * 100)}%</span>}
                  {lr.blockers > 0 ? (
                    <span className="rounded-full bg-[var(--vt-blocker-bg)] px-1.5 font-semibold tabular-nums text-[var(--vt-blocker)]">{lr.blockers} must-fix</span>
                  ) : lr.warnings > 0 ? <span className="text-muted">{lr.warnings} to fix</span> : <span className="text-[var(--vt-ok)]">Clean</span>}
                </span>
              )}
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-xs">
        <span className="flex items-center gap-2">
          {(r.open_escalations ?? 0) > 0 && (
            <span className="inline-flex items-center gap-1 rounded-md bg-accent/12 px-1.5 py-0.5 font-medium text-accent" title="The creator asked a person to look">
              <InboxIcon size={12} /> Asked
            </span>
          )}
          {r.rechecked_for_event != null && (
            <span className="inline-flex items-center gap-1 text-muted" title="Re-checked after a brand event changed"><RefreshIcon size={12} /> Event</span>
          )}
          {!(r.open_escalations ?? 0) && r.rechecked_for_event == null && <span className="text-subtle">-</span>}
        </span>
      </td>
      <td className="whitespace-nowrap px-3 py-2.5 text-xs text-muted">{relativeTime(queue === "waiting" ? sinceOf(r) : r.updated_at ?? r.created_at)}</td>
      <td className="py-2.5 pr-4 md:pr-5">
        <ArrowRightIcon size={14} className="text-subtle transition group-hover:translate-x-0.5 group-hover:text-ink" />
      </td>
    </tr>
  );
}

function groupRows(rows: ContentRow[], group: Group, nameOf: (id: number) => string,
  eventName: Map<number, string>): [string, ContentRow[]][] {
  if (group === "none") return [["", rows]];
  const key = (r: ContentRow) => group === "creator" ? nameOf(r.created_by)
    : group === "event" ? (r.event_id ? eventName.get(r.event_id) ?? "Event" : "Not for an event")
      : group === "channel" ? r.channel.replace("_", " ")
        : STATUS_LABEL[r.status];
  const map = new Map<string, ContentRow[]>();
  for (const r of rows) map.set(key(r), [...(map.get(key(r)) ?? []), r]);
  const entries = [...map.entries()];
  if (group === "stage") entries.sort((a, b) => STAGE_ORDER.indexOf(a[1][0].status) - STAGE_ORDER.indexOf(b[1][0].status));
  else entries.sort((a, b) => a[0].localeCompare(b[0]));
  return entries;
}

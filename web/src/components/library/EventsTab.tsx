"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { cancelEvent, createEvent, eventImpacts, relativeTime, updateEvent } from "@/lib/review-client";
import type { BrandEvent, EventImpact, EventKind } from "@/lib/types";
import { CalendarIcon, PlusIcon, RefreshIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field, today, toList } from "./parts";

const KINDS: Record<EventKind, string> = {
  launch: "Launch", campaign: "Campaign", sale: "Sale", crisis: "Crisis", partnership: "Partnership", other: "Other",
};

type When = "live" | "upcoming" | "past" | "cancelled";
function whenOf(e: BrandEvent, on: string): When {
  if (e.status === "cancelled") return "cancelled";
  if (e.starts_on > on) return "upcoming";
  if (e.ends_on && e.ends_on < on) return "past";
  return "live";
}
const WHEN: Record<When, { label: string; tone: "ok" | "accent" | "muted" | "warning" }> = {
  live: { label: "Running", tone: "ok" }, upcoming: { label: "Scheduled", tone: "accent" },
  past: { label: "Ended", tone: "muted" }, cancelled: { label: "Cancelled", tone: "muted" },
};

/**
 * What the brand is doing or going through. An event is written once and then
 * reaches every review by itself: saving it rewrites the rules it owns (its
 * brief, the words to avoid, its hashtag) and re-checks the pieces in flight.
 */
export function EventsTab({ events, editable, onChanged }: { events: BrandEvent[]; editable: boolean; onChanged: () => void }) {
  const [form, setForm] = useState<Partial<BrandEvent> | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const on = today();
  const order: When[] = ["live", "upcoming", "past", "cancelled"];
  const sorted = [...events].sort((a, b) => order.indexOf(whenOf(a, on)) - order.indexOf(whenOf(b, on))
    || a.starts_on.localeCompare(b.starts_on));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="max-w-xl text-xs leading-5 text-muted">
          Saving an event rewrites its rules and re-checks every piece in review, so the queue always reflects what the brand is doing now.
        </p>
        {editable && (
          <button type="button" onClick={() => setForm({ kind: "campaign", starts_on: on, hashtags: [], avoid_terms: [] })}
            className="vt-btn vt-btn-primary ml-auto py-1.5"><PlusIcon size={14} /> New event</button>
        )}
      </div>
      {form && <EventForm initial={form} onCancel={() => setForm(null)} onDone={() => { setForm(null); onChanged(); }} />}
      {sorted.length === 0 ? <Empty>No events yet. Add a launch, a sale or a crisis, and every review takes it into account.</Empty> : (
        <ul className="overflow-hidden rounded-xl border border-line bg-raised">
          {sorted.map((e) => {
            const w = whenOf(e, on);
            return (
              <li key={e.id} className="border-b border-line last:border-0">
                <button type="button" onClick={() => setOpen(open === e.id ? null : e.id)} aria-expanded={open === e.id}
                  className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-sunken/50">
                  <CalendarIcon size={16} className="shrink-0 text-subtle" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{e.name}</span>
                    <span className="block truncate text-[11px] text-subtle">
                      {KINDS[e.kind]} · {e.starts_on}{e.ends_on ? ` to ${e.ends_on}` : " onwards"}
                      {e.pieces ? ` · ${e.pieces} piece${e.pieces === 1 ? "" : "s"} made for it` : ""}
                      {e.revision > 1 ? ` · revision ${e.revision}` : ""}
                    </span>
                  </span>
                  {e.blackout && w !== "cancelled" && <Badge tone="warning">Blackout</Badge>}
                  <Badge tone={WHEN[w].tone}>{WHEN[w].label}</Badge>
                </button>
                {open === e.id && <EventDetail event={e} editable={editable && w !== "cancelled"} onEdit={() => setForm(e)} onChanged={onChanged} />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function EventDetail({ event, editable, onEdit, onChanged }: { event: BrandEvent; editable: boolean; onEdit: () => void; onChanged: () => void }) {
  const [impacts, setImpacts] = useState<EventImpact[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const toast = useToast();
  useEffect(() => {
    let live = true;
    eventImpacts(event.id).then((x) => { if (live) setImpacts(x); }).catch(() => { if (live) setImpacts([]); });
    return () => { live = false; };
  }, [event.id, event.revision]);
  return (
    <div className="vt-pop grid gap-5 border-t border-line px-4 py-4 text-sm md:grid-cols-2">
      <div className="flex flex-col gap-3">
        {event.summary && <p className="leading-6">{event.summary}</p>}
        {event.guidance && <p className="rounded-lg bg-sunken px-3 py-2 text-xs leading-5 text-muted"><span className="font-medium text-ink">Brief: </span>{event.guidance}</p>}
        <div className="flex flex-wrap gap-1.5 text-xs">
          {event.hashtags.map((t) => <Badge key={t} tone="accent">{t.startsWith("#") ? t : `#${t}`}</Badge>)}
          {event.avoid_terms.map((t) => <Badge key={t} tone="blocker">avoid: {t}</Badge>)}
        </div>
        {event.rules.length > 0 && (
          <p className="text-[11px] text-subtle">Rules it owns: {event.rules.map((r) => <code key={r} className="mr-1.5">{r}</code>)}</p>
        )}
        {editable && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onEdit} className="vt-btn vt-btn-quiet py-1.5">Edit</button>
            {confirm ? (
              <span className="vt-pop flex items-center gap-1.5 text-xs">
                <span className="text-[var(--vt-blocker)]">Cancel the event and retire its rules?</span>
                <button type="button" disabled={busy} className="vt-btn px-2 py-1 text-xs text-[var(--vt-blocker)]" onClick={async () => {
                  setBusy(true);
                  try {
                    const out = await cancelEvent(event.id);
                    toast({ kind: "success", title: "Event cancelled", detail: `${out.rechecked.length} piece${out.rechecked.length === 1 ? "" : "s"} re-checked.` });
                    onChanged();
                  } catch (err) {
                    toast({ kind: "error", title: "Couldn't cancel it", detail: (err as Error).message });
                  } finally {
                    setBusy(false);
                  }
                }}>Cancel event</button>
                <button type="button" onClick={() => setConfirm(false)} className="vt-btn vt-btn-quiet px-2 py-1 text-xs">Keep</button>
              </span>
            ) : <button type="button" onClick={() => setConfirm(true)} className="vt-btn py-1.5 text-subtle hover:text-[var(--vt-blocker)]">Cancel event</button>}
          </div>
        )}
      </div>
      <div>
        <p className="mb-2 flex items-center gap-1.5 text-xs font-medium"><RefreshIcon size={13} className="text-accent" /> Update chain</p>
        {impacts === null ? <div className="h-16 animate-pulse rounded-lg bg-sunken" /> : impacts.length === 0 ? (
          <p className="text-xs text-muted">No piece needed a re-check yet.</p>
        ) : (
          <ul className="flex max-h-56 flex-col gap-1.5 overflow-y-auto text-xs">
            {impacts.map((i, n) => (
              <li key={`${i.content_id}-${i.revision}-${n}`} className="flex items-center gap-2">
                <span className="w-16 shrink-0 text-subtle">rev. {i.revision}</span>
                <Link href={`/review?queue=all&id=${i.content_id}`} className="min-w-0 flex-1 truncate hover:text-accent">{i.title}</Link>
                <span className={`shrink-0 tabular-nums ${i.blockers ? "text-[var(--vt-blocker)]" : "text-muted"}`}>
                  {i.review_status !== "done" ? (i.review_status ?? "queued") : i.blockers ? `${i.blockers} must-fix` : "clean"}
                </span>
                <span className="w-16 shrink-0 text-right text-subtle">{relativeTime(i.at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function EventForm({ initial, onCancel, onDone }: { initial: Partial<BrandEvent>; onCancel: () => void; onDone: () => void }) {
  const editing = initial.id != null;
  const [e, setE] = useState({
    name: initial.name ?? "", kind: (initial.kind ?? "campaign") as EventKind, starts_on: initial.starts_on ?? today(),
    ends_on: initial.ends_on ?? "", summary: initial.summary ?? "", guidance: initial.guidance ?? "",
    hashtags: (initial.hashtags ?? []).join(", "), avoid_terms: (initial.avoid_terms ?? []).join(", "), blackout: initial.blackout ?? false,
  });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (p: Partial<typeof e>) => setE((x) => ({ ...x, ...p }));

  async function save() {
    setBusy(true);
    const body = { ...e, name: e.name.trim(), ends_on: e.ends_on || null, hashtags: toList(e.hashtags), avoid_terms: toList(e.avoid_terms) };
    try {
      const out = editing ? await updateEvent(initial.id!, body) : await createEvent(body);
      toast({ kind: "success", title: editing ? "Event updated" : "Event added",
        detail: out.rechecked.length ? `${out.rechecked.length} piece${out.rechecked.length === 1 ? "" : "s"} re-checked against it.` : "Its rules are live." });
      onDone();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't save the event", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="vt-pop vt-card flex flex-col gap-4 p-5" aria-label={editing ? "Edit event" : "New event"}>
      <div className="grid gap-3 md:grid-cols-[1fr_10rem_10rem_10rem]">
        <Field label="Name"><input value={e.name} onChange={(x) => set({ name: x.target.value })} maxLength={160} placeholder="Festive Learning Fest" className="vt-input" /></Field>
        <Field label="Kind">
          <select value={e.kind} onChange={(x) => set({ kind: x.target.value as EventKind })} className="vt-input">
            {(Object.keys(KINDS) as EventKind[]).map((k) => <option key={k} value={k}>{KINDS[k]}</option>)}
          </select>
        </Field>
        <Field label="Starts"><input type="date" value={e.starts_on} onChange={(x) => set({ starts_on: x.target.value })} className="vt-input" /></Field>
        <Field label="Ends" hint="optional"><input type="date" value={e.ends_on} onChange={(x) => set({ ends_on: x.target.value })} className="vt-input" /></Field>
      </div>
      <Field label="What it is" hint="optional">
        <input value={e.summary} onChange={(x) => set({ summary: x.target.value })} maxLength={4000} placeholder="30% off annual plans across the festive week" className="vt-input" />
      </Field>
      <Field label="Brief for posts" hint="what posts should and shouldn't say while it runs">
        <textarea value={e.guidance} onChange={(x) => set({ guidance: x.target.value })} maxLength={4000}
          placeholder="Lead with what learners gain; the discount comes second. No countdown pressure." className="vt-input min-h-16" />
      </Field>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Hashtags" hint="comma separated; required on pieces made for it">
          <input value={e.hashtags} onChange={(x) => set({ hashtags: x.target.value })} placeholder="#LearnThisFestive" className="vt-input" />
        </Field>
        <Field label="Words to avoid" hint="comma separated; flagged while it runs">
          <input value={e.avoid_terms} onChange={(x) => set({ avoid_terms: x.target.value })} placeholder="cheapest, lowest price ever" className="vt-input" />
        </Field>
      </div>
      <label className="flex items-start gap-2.5 text-sm">
        <input type="checkbox" checked={e.blackout} onChange={(x) => set({ blackout: x.target.checked })} className="mt-0.5 h-4 w-4" />
        <span><span className="font-medium">Blackout</span><span className="block text-xs text-muted">Pause promotional posts while it runs, for a crisis or a day of mourning.</span></span>
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" disabled={busy || e.name.trim().length < 2 || !e.starts_on} onClick={save} className="vt-btn vt-btn-primary py-1.5">
          {busy ? "Saving..." : editing ? "Save and re-check" : "Add event"}
        </button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet py-1.5">Cancel</button>
        <span className="text-[11px] text-subtle">Pieces in review are re-checked against the new version.</span>
      </div>
    </section>
  );
}

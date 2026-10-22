"use client";

import { type PointerEvent as ReactPointerEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError, listContents, listEscalations, listEvents, listPeople } from "@/lib/review-client";
import { useStored, writeStored } from "@/lib/stored";
import type { BrandEvent, EscalationRequest, Overview, Person, Recurring, RuleHealth } from "@/lib/types";
import { ChevronIcon, CloseIcon, GripIcon, PlusIcon } from "../Icons";
import { useViewer } from "../Viewer";
import { type DashData, DEFAULT_LAYOUT, type Size, WIDGETS, WidgetPanel } from "./widgets";

type Item = { id: string; size: Size };
const HOLD_MS = 550; // press and hold on a widget to start editing, as on a phone's home screen
const EDIT_EVENT = "vt-dashboard-edit";

/** Sits in the page header; the dashboard below listens for it. */
export function CustomizeButton() {
  return (
    <button type="button" onClick={() => window.dispatchEvent(new Event(EDIT_EVENT))} className="vt-btn vt-btn-quiet py-1.5 text-xs">
      Customize
    </button>
  );
}

function parse(raw: string | null): Item[] | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as { items?: Item[] };
    const items = (v.items ?? []).filter((i) => i && Object.hasOwn(WIDGETS, i.id) && (i.size === "half" || i.size === "full"));
    return items.length ? items.filter((i, n) => items.findIndex((x) => x.id === i.id) === n) : null;
  } catch {
    return null;
  }
}

/**
 * The brand team's dashboard, arranged by each person. "Customize" (or a long
 * press on any widget) starts editing: widgets wobble, can be dragged into a new
 * order, resized, removed, or added back from the tray. Every move animates from
 * where the widget was, so the eye can follow it. The layout is a per-person,
 * per-browser preference, so it lives in local storage.
 */
export function ManagerDashboard({ overview, recurring, health }: { overview: Overview; recurring: Recurring[]; health: RuleHealth[] }) {
  const { me } = useViewer();
  const key = `vt-dashboard:${me?.id ?? "anon"}`;
  const stored = useStored(key);
  const layout = useMemo(() => parse(stored) ?? DEFAULT_LAYOUT, [stored]);
  const [editing, setEditing] = useState(false);
  const [dragging, setDragging] = useState<string | null>(null);
  const [data, setData] = useState<Omit<DashData, "overview" | "recurring" | "health">>({
    rows: null, people: new Map(), escalations: null, events: null, demo: false });

  useEffect(() => {
    let live = true;
    listContents(false).then((rows) => live && setData((d) => ({ ...d, rows }))).catch((err) => {
      if (live) setData((d) => ({ ...d, rows: [], demo: err instanceof ApiError && err.status === 503 }));
    });
    listPeople().then((ps) => live && setData((d) => ({ ...d, people: new Map(ps.map((p: Person) => [p.id, p])) }))).catch(() => {});
    listEscalations("open").then((e: EscalationRequest[]) => live && setData((d) => ({ ...d, escalations: e })))
      .catch(() => live && setData((d) => ({ ...d, escalations: [] })));
    listEvents().then((e: BrandEvent[]) => live && setData((d) => ({ ...d, events: e })))
      .catch(() => live && setData((d) => ({ ...d, events: [] })));
    return () => { live = false; };
  }, []);
  const d: DashData = { overview, recurring, health, ...data };

  // FLIP: remember where every widget was before a change, then animate each from there to its new place.
  const nodes = useRef(new Map<string, HTMLElement>());
  const before = useRef(new Map<string, DOMRect>());
  const save = useCallback((items: Item[]) => {
    before.current = new Map([...nodes.current].map(([k, el]) => [k, el.getBoundingClientRect()]));
    writeStored(key, JSON.stringify({ v: 1, items }));
  }, [key]);
  useLayoutEffect(() => {
    if (!before.current.size) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const [k, el] of nodes.current) {
      const was = before.current.get(k);
      if (!was || still) continue;
      const now = el.getBoundingClientRect();
      const dx = was.left - now.left, dy = was.top - now.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
      el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
        { duration: 280, easing: "cubic-bezier(0.16, 1, 0.3, 1)" });
    }
    before.current = new Map();
  }, [layout]);

  const move = (id: string, to: number) => {
    const from = layout.findIndex((i) => i.id === id);
    if (from < 0 || to < 0 || to >= layout.length || from === to) return;
    const next = [...layout];
    const [it] = next.splice(from, 1);
    next.splice(to, 0, it);
    save(next);
  };
  const resize = (id: string) => save(layout.map((i) => (i.id === id ? { ...i, size: i.size === "full" ? "half" : "full" } : i)));
  const remove = (id: string) => save(layout.filter((i) => i.id !== id));
  const add = (id: string) => save([...layout, { id, size: WIDGETS[id].size }]);
  const hidden = Object.keys(WIDGETS).filter((id) => !layout.some((i) => i.id === id));

  // Dragging: the widget under the pointer gives up its place to the one being dragged.
  const hold = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSwap = useRef<string | null>(null);
  const onDown = (e: ReactPointerEvent<HTMLElement>, id: string) => {
    if ((e.target as HTMLElement).closest("button, a, input, select, textarea") && editing) return;
    if (!editing) {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      hold.current = setTimeout(() => setEditing(true), HOLD_MS);
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    setDragging(id);
    lastSwap.current = null;
  };
  const onMove = (e: ReactPointerEvent<HTMLElement>) => {
    if (hold.current && (Math.abs(e.movementX) + Math.abs(e.movementY) > 3)) { clearTimeout(hold.current); hold.current = null; }
    if (!dragging) return;
    const over = document.elementsFromPoint(e.clientX, e.clientY).map((el) => el.closest<HTMLElement>("[data-widget]"))
      .find((el) => el && el.dataset.widget !== dragging);
    const target = over?.dataset.widget;
    if (!target || target === lastSwap.current) return;
    lastSwap.current = target;
    move(dragging, layout.findIndex((i) => i.id === target));
  };
  const onUp = () => {
    if (hold.current) { clearTimeout(hold.current); hold.current = null; }
    setDragging(null);
    lastSwap.current = null;
  };
  useEffect(() => {
    const start = () => setEditing(true);
    window.addEventListener(EDIT_EVENT, start);
    return () => window.removeEventListener(EDIT_EVENT, start);
  }, []);
  useEffect(() => {
    if (!editing) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setEditing(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing]);

  return (
    <div className="flex flex-col gap-4">
      {editing && (
        <div className="vt-pop sticky top-3 z-20 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-raised/95 px-4 py-2.5 shadow-[var(--vt-shadow-pop)] backdrop-blur"
          role="toolbar" aria-label="Dashboard layout">
          <p className="mr-auto text-xs text-muted" role="status">Drag widgets to reorder; the corner buttons resize or remove them. Esc to finish.</p>
          <button type="button" onClick={() => save(DEFAULT_LAYOUT)} className="vt-btn vt-btn-quiet py-1.5 text-xs">Reset to default</button>
          <button type="button" onClick={() => setEditing(false)} className="vt-btn vt-btn-primary py-1.5">Done</button>
        </div>
      )}

      <div className="grid items-start gap-5 xl:grid-cols-2" aria-live="polite">
        {layout.map((item, n) => (
          <div key={item.id} data-widget={item.id}
            ref={(el) => { if (el) nodes.current.set(item.id, el); else nodes.current.delete(item.id); }}
            className={`relative min-w-0 rounded-[14px] transition-shadow ${item.size === "full" ? "xl:col-span-2" : ""} ${
              editing ? "touch-none select-none" : ""} ${dragging === item.id ? "vt-dragging" : ""}`}
            onPointerDown={(e) => onDown(e, item.id)} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
            <div className={`h-full rounded-[14px] ${editing ? "vt-wobble cursor-grab outline-dashed outline-1 outline-offset-4 outline-line-strong" : ""}`}
              style={editing ? { ["--vt-wobble-delay" as string]: `${(n * 97) % 380}ms`, animationDirection: n % 2 ? "reverse" : "normal" } : undefined}>
              <div className={editing ? "pointer-events-none" : ""} aria-hidden={editing || undefined}>
                <WidgetPanel id={item.id} d={d} editing={editing} />
              </div>
            </div>
            {editing && (
              <div className="vt-pop absolute -right-2 -top-2 z-10 flex items-center gap-1 rounded-full border border-line bg-raised p-1 shadow-[var(--vt-shadow-pop)]">
                <span className="grid h-7 w-7 place-items-center text-subtle" aria-hidden><GripIcon size={14} /></span>
                <button type="button" onClick={() => move(item.id, n - 1)} disabled={n === 0} aria-label={`Move ${WIDGETS[item.id].title} earlier`}
                  className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-sunken hover:text-ink disabled:opacity-30">
                  <ChevronIcon size={14} className="rotate-90" />
                </button>
                <button type="button" onClick={() => move(item.id, n + 1)} disabled={n === layout.length - 1} aria-label={`Move ${WIDGETS[item.id].title} later`}
                  className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-sunken hover:text-ink disabled:opacity-30">
                  <ChevronIcon size={14} className="-rotate-90" />
                </button>
                <button type="button" onClick={() => resize(item.id)} aria-label={`Make ${WIDGETS[item.id].title} ${item.size === "full" ? "half" : "full"} width`}
                  className="hidden h-7 rounded-full px-2 text-[11px] font-medium text-muted hover:bg-sunken hover:text-ink xl:block">
                  {item.size === "full" ? "Half" : "Full"}
                </button>
                <button type="button" onClick={() => remove(item.id)} aria-label={`Remove ${WIDGETS[item.id].title}`}
                  className="grid h-7 w-7 place-items-center rounded-full text-muted hover:bg-[var(--vt-blocker-bg)] hover:text-[var(--vt-blocker)]">
                  <CloseIcon size={14} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {editing && (
        <section className="vt-pop rounded-[14px] border border-dashed border-line-strong p-4 md:p-5" aria-label="Add a widget">
          <h2 className="text-sm font-semibold">Add a widget</h2>
          {hidden.length === 0 ? <p className="mt-2 text-sm text-muted">Everything is on your dashboard.</p> : (
            <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {hidden.map((id) => (
                <li key={id}>
                  <button type="button" onClick={() => add(id)}
                    className="flex w-full items-start gap-3 rounded-xl border border-line bg-raised p-3 text-left transition-colors hover:border-accent">
                    <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent/12 text-accent"><PlusIcon size={13} /></span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{WIDGETS[id].title}</span>
                      <span className="block text-xs text-muted">{WIDGETS[id].blurb}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}


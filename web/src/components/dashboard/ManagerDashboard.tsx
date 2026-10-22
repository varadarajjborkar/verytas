"use client";

import { type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ApiError, listContents, listCreators, listEscalations, listEvents, listPeople } from "@/lib/review-client";
import { useStored, writeStored } from "@/lib/stored";
import type { BrandEvent, EscalationRequest, Overview, Person, Recurring, RuleHealth } from "@/lib/types";
import { CloseIcon, GripIcon, PlusIcon } from "../Icons";
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
 * The brand team's dashboard, arranged by each person. "Customize" (or a long press on any widget)
 * turns every widget into a small named tile, as a phone's home screen does: the charts would make
 * dragging slow and the page too tall to see where things land. A tile follows the pointer, its
 * neighbours slide aside, and the order is saved once, on drop. The layout is a per-person,
 * per-browser preference, so it lives in local storage.
 */
export function ManagerDashboard({ overview, recurring, health }: { overview: Overview; recurring: Recurring[]; health: RuleHealth[] }) {
  const { me, loading } = useViewer();
  const key = `vt-dashboard:${me?.id ?? "anon"}`;
  const stored = useStored(key);
  const layout = useMemo(() => parse(stored) ?? DEFAULT_LAYOUT, [stored]);
  const [editing, setEditing] = useState(false);
  const [data, setData] = useState<Omit<DashData, "overview" | "recurring" | "health">>({
    rows: null, people: new Map(), escalations: null, events: null, creators: null, demo: false });

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
    listCreators().then((c) => live && setData((d) => ({ ...d, creators: c })))
      .catch(() => live && setData((d) => ({ ...d, creators: [] })));
    return () => { live = false; };
  }, []);
  const d: DashData = { overview, recurring, health, ...data };

  const hold = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelHold = () => { if (hold.current) { clearTimeout(hold.current); hold.current = null; } };
  const onHoldStart = (e: ReactPointerEvent<HTMLElement>) => {
    // A long press on a link or button is that control's, not a request to start editing.
    if ((e.target as HTMLElement).closest("button, a, input, select, textarea")) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    hold.current = setTimeout(() => setEditing(true), HOLD_MS);
  };
  useEffect(() => {
    const start = () => setEditing(true);
    window.addEventListener(EDIT_EVENT, start);
    return () => window.removeEventListener(EDIT_EVENT, start);
  }, []);

  // Until the account is known the layout key is too, and the default would flash before the saved one.
  if (loading) {
    return <div aria-busy="true" aria-label="Loading" className="grid gap-5 xl:grid-cols-2">
      {[0, 1, 2, 3].map((i) => <div key={i} className={`h-48 animate-pulse rounded-[14px] bg-sunken ${i === 0 ? "xl:col-span-2" : ""}`} />)}
    </div>;
  }
  if (editing) {
    return <Arrange layout={layout} onSave={(items) => writeStored(key, items ? JSON.stringify({ v: 1, items }) : null)} onDone={() => setEditing(false)} />;
  }
  const panel = (item: Item, order: number) => (
    <div key={item.id} style={{ order }} className="min-w-0"
      onPointerDown={onHoldStart} onPointerMove={(e) => { if (Math.abs(e.movementX) + Math.abs(e.movementY) > 3) cancelHold(); }}
      onPointerUp={cancelHold} onPointerCancel={cancelHold} onPointerLeave={cancelHold}>
      <WidgetPanel id={item.id} d={d} />
    </div>
  );
  // Half-width widgets alternate between two columns that stack independently, so a short widget
  // never leaves a hole beside a tall one. Below xl the columns dissolve (display: contents) and
  // `order` restores the saved sequence in the single column.
  return (
    <div className="grid gap-5">
      {runs(layout).map((run, n) => run.full ? panel(run.full, 0) : (
        <div key={`run-${n}`} className="grid gap-5 xl:grid-cols-2">
          {[0, 1].map((side) => (
            <div key={side} className="contents xl:flex xl:flex-col xl:gap-5">
              {run.halves.map((item, i) => i % 2 === side ? panel(item, i) : null)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/** The layout cut at each full-width widget: runs of halves between them. */
function runs(layout: Item[]): ({ full: Item; halves?: never } | { full?: never; halves: Item[] })[] {
  const out: ({ full: Item; halves?: never } | { full?: never; halves: Item[] })[] = [];
  for (const item of layout) {
    const last = out.at(-1);
    if (item.size === "full") out.push({ full: item });
    else if (last?.halves) last.halves.push(item);
    else out.push({ halves: [item] });
  }
  return out;
}

type Drag = { id: string; pointer: number; mouse: boolean; start: string; grabX: number; grabY: number; x: number; y: number;
  clientY: number; frame: number };
const EDGE = 64; // px from the top or bottom of the window where a drag scrolls the page
const ids = (items: Item[]) => items.map((i) => i.id).join(",");

/** The arranging view: light tiles in the dashboard's own grid, so what you see is where it lands. */
function Arrange({ layout, onSave, onDone }: { layout: Item[]; onSave: (items: Item[] | null) => void; onDone: () => void }) {
  const [order, setOrder] = useState(layout);
  const [dragging, setDragging] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const grid = useRef<HTMLDivElement>(null);
  const tiles = useRef(new Map<string, HTMLElement>());
  const drag = useRef<Drag | null>(null);
  const orderRef = useRef(order);
  const before = useRef(new Map<string, DOMRect>());
  const lastOver = useRef<string | null>(null);
  const hidden = Object.keys(WIDGETS).filter((id) => !order.some((i) => i.id === id));
  const title = (id: string) => WIDGETS[id].title;

  // Neighbours slide from where they were (FLIP); the dragged tile is placed under the pointer instead.
  const reorder = (next: Item[]) => {
    before.current = new Map([...tiles.current].map(([k, el]) => [k, el.getBoundingClientRect()]));
    setOrder(next);
  };
  useLayoutEffect(() => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const [k, el] of tiles.current) {
      const was = before.current.get(k);
      if (!was || still || k === drag.current?.id) continue;
      const now = el.getBoundingClientRect();
      const dx = was.left - now.left, dy = was.top - now.top;
      if (Math.abs(dx) + Math.abs(dy) < 1) continue;
      el.animate([{ translate: `${dx}px ${dy}px` }, { translate: "0 0" }], { duration: 200, easing: "cubic-bezier(0.2, 0, 0, 1)" });
    }
    before.current = new Map();
    orderRef.current = order;
    place();
  }, [order]);

  // The dragged tile is moved with `translate` straight from the pointer, outside React: nothing re-renders
  // while it moves. offsetLeft/Top ignore transforms, so they give the tile's slot in the grid.
  function place() {
    const g = drag.current, el = g && tiles.current.get(g.id);
    if (!g || !el) return;
    el.style.translate = `${g.x - g.grabX - el.offsetLeft}px ${g.y - g.grabY - el.offsetTop}px`;
  }
  // A mouse drags a tile from anywhere on it. On touch only the grip drags, so the rest of a tile still scrolls the
  // page (tiles allow vertical panning; the grip doesn't).
  const onDown = (e: ReactPointerEvent<HTMLElement>, id: string) => {
    const target = e.target as HTMLElement;
    if (drag.current || target.closest("button") || (e.pointerType === "mouse" && e.button !== 0)) return;
    if (e.pointerType !== "mouse" && !target.closest("[data-grip]")) return;
    const el = tiles.current.get(id), box = grid.current?.getBoundingClientRect();
    if (!el || !box) return;
    e.preventDefault();
    el.focus({ preventScroll: true }); // preventDefault would otherwise keep the click from focusing the tile
    const x = e.clientX - box.left, y = e.clientY - box.top;
    drag.current = { id, pointer: e.pointerId, mouse: e.pointerType === "mouse", start: ids(orderRef.current),
      grabX: x - el.offsetLeft, grabY: y - el.offsetTop, x, y, clientY: e.clientY, frame: 0 };
    lastOver.current = null;
    setDragging(id);
  };
  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: PointerEvent) => {
      const g = drag.current;
      if (!g || e.pointerId !== g.pointer) return;
      if (g.mouse && e.buttons === 0) { onUp(); return; } // the button came up outside the window
      g.clientY = e.clientY;
      const box = grid.current?.getBoundingClientRect();
      if (box) g.x = e.clientX - box.left;
      track();
    };
    // Follows the pointer, and keeps scrolling while it rests near the window's top or bottom edge.
    const track = () => {
      const g = drag.current, box = grid.current?.getBoundingClientRect();
      if (!g || !box || g.frame) return;
      g.frame = requestAnimationFrame(() => {
        g.frame = 0;
        const edge = g.clientY < EDGE ? -1 : g.clientY > window.innerHeight - EDGE ? 1 : 0;
        if (edge) window.scrollBy(0, edge * 12);
        const now = grid.current?.getBoundingClientRect();
        if (!now) return;
        g.y = g.clientY - now.top;
        if (edge) track();
        place();
        // The slot under the pointer, read from the grid's layout rather than from what is on screen mid-slide.
        const over = orderRef.current.find(({ id }) => {
          const t = tiles.current.get(id);
          return id !== g.id && t && g.x >= t.offsetLeft && g.x <= t.offsetLeft + t.offsetWidth
            && g.y >= t.offsetTop && g.y <= t.offsetTop + t.offsetHeight;
        })?.id ?? null;
        // A swap moves the other tile under the pointer's old ground; waiting until the pointer leaves it stops a flicker.
        if (!over || over === lastOver.current) { if (!over) lastOver.current = null; return; }
        lastOver.current = over;
        const cur = orderRef.current, from = cur.findIndex((i) => i.id === g.id), to = cur.findIndex((i) => i.id === over);
        const next = [...cur];
        next.splice(to, 0, ...next.splice(from, 1));
        reorder(next);
      });
    };
    const end = (e?: PointerEvent) => {
      if (e && drag.current && e.pointerId !== drag.current.pointer) return;
      onUp();
    };
    function onUp() {
      const g = drag.current, el = g && tiles.current.get(g.id);
      if (g?.frame) cancelAnimationFrame(g.frame);
      if (el) {
        const from = el.style.translate || "0 0";
        el.style.translate = "";
        el.animate([{ translate: from }, { translate: "0 0" }], { duration: 160, easing: "cubic-bezier(0.2, 0, 0, 1)" });
      }
      drag.current = null;
      setDragging(null);
      // A press without a move changes nothing, and saving it would pin today's default as the user's own layout.
      if (g && ids(orderRef.current) !== g.start) onSave(orderRef.current);
    }
    const hiddenTab = () => { if (document.hidden) onUp(); };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", end);
    window.addEventListener("pointercancel", end);
    window.addEventListener("blur", onUp);
    document.addEventListener("visibilitychange", hiddenTab);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", end);
      window.removeEventListener("pointercancel", end);
      window.removeEventListener("blur", onUp);
      document.removeEventListener("visibilitychange", hiddenTab);
    };
  // place and reorder only touch refs and stable setters.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragging]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onDone(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDone]);

  const commit = (next: Item[], message: string, focus?: string) => {
    reorder(next);
    onSave(next);
    setSaid(message);
    // Keep the keyboard where the user is working, rather than dropping focus to the page.
    if (focus) requestAnimationFrame(() => tiles.current.get(focus)?.focus());
  };
  const remove = (id: string) => {
    const n = order.findIndex((i) => i.id === id), next = order.filter((i) => i.id !== id);
    commit(next, `${title(id)} removed`, next[Math.min(n, next.length - 1)]?.id);
  };
  const add = (id: string) => commit([...order, { id, size: WIDGETS[id].size }], `${title(id)} added at the end`, id);
  // Reset forgets the saved layout, so later changes to the default reach this person too.
  const reset = () => { reorder(DEFAULT_LAYOUT); onSave(null); setSaid("Default layout restored");
    requestAnimationFrame(() => tiles.current.get(DEFAULT_LAYOUT[0].id)?.focus()); };
  // Keyboard: arrows move the focused tile, Delete removes it.
  const onKey = (e: ReactKeyboardEvent, id: string) => {
    const n = order.findIndex((i) => i.id === id);
    const step = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : 0;
    if (step && n + step >= 0 && n + step < order.length) {
      e.preventDefault();
      const next = [...order];
      next.splice(n + step, 0, ...next.splice(n, 1));
      commit(next, `${title(id)} moved to place ${n + step + 1} of ${order.length}`);
      requestAnimationFrame(() => tiles.current.get(id)?.focus());
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      remove(id);
    }
  };

  return (
    <div className="vt-page flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <p className="mr-auto text-sm text-muted">Drag tiles to rearrange.</p>
        <button type="button" onClick={reset} className="text-xs font-medium text-subtle hover:text-ink">
          Reset
        </button>
        <button type="button" onClick={onDone} className="vt-btn vt-btn-primary py-1.5">Done</button>
      </div>
      <p className="sr-only" role="status" aria-live="polite">{said}</p>

      <div ref={grid} role="list" aria-label="Dashboard widgets" className="relative grid gap-3 sm:grid-cols-2 xl:gap-4">
        {order.map((item, n) => (
          <div key={item.id} role="listitem" tabIndex={0} aria-roledescription="movable widget"
            aria-label={`${title(item.id)}, place ${n + 1} of ${order.length}. Arrow keys move it, Delete removes it.`}
            ref={(el) => { if (el) tiles.current.set(item.id, el); else tiles.current.delete(item.id); }}
            onPointerDown={(e) => onDown(e, item.id)} onKeyDown={(e) => onKey(e, item.id)}
            className={`relative flex h-[72px] touch-pan-y select-none items-center gap-3 rounded-xl border bg-raised px-4 outline-offset-2 ${
              item.size === "full" ? "sm:col-span-2" : ""} ${dragging === item.id
              ? "vt-dragging z-10 cursor-grabbing border-accent" : "vt-wobble cursor-grab border-line hover:border-line-strong"}`}
            style={dragging === item.id ? undefined : { ["--vt-wobble-delay" as string]: `${(n * 83) % 320}ms` }}>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{title(item.id)}</span>
              <span className="block truncate text-xs text-muted">{WIDGETS[item.id].blurb}</span>
            </span>
            <span data-grip aria-hidden className="-mr-2 grid h-10 w-10 shrink-0 touch-none place-items-center text-subtle">
              <GripIcon size={15} />
            </span>
            <button type="button" onClick={() => remove(item.id)} aria-label={`Remove ${title(item.id)}`} tabIndex={-1}
              className="absolute -left-2 -top-2 grid h-6 w-6 place-items-center rounded-full border border-line bg-raised text-muted shadow-sm transition-colors hover:border-[var(--vt-blocker)] hover:text-[var(--vt-blocker)]">
              <CloseIcon size={11} />
            </button>
          </div>
        ))}
      </div>

      {hidden.length > 0 && (
        <section aria-label="Hidden widgets" className="flex flex-col gap-2 pt-1">
          <h2 className="text-xs font-medium text-subtle">Hidden</h2>
          <ul className="flex flex-wrap gap-2">
            {hidden.map((id) => (
              <li key={id}>
                <button type="button" onClick={() => add(id)} title={WIDGETS[id].blurb}
                  className="flex items-center gap-1.5 rounded-full border border-line bg-raised py-1.5 pl-2 pr-3 text-xs font-medium transition-colors hover:border-accent hover:text-accent">
                  <PlusIcon size={12} /> {title(id)}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

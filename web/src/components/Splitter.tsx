"use client";

import { useEffect, useRef, useState } from "react";
import { useStored, writeStored } from "@/lib/stored";

/**
 * The width of a side pane its reader can drag, remembered per browser. Returns the width to apply and the
 * handle that sets it; the handle sits on the pane's edge. Writes to storage only when a drag ends, so a
 * drag repaints this pane alone instead of every reader of the stored value.
 */
export function useSplit(key: string, { initial, min, max }: { initial: number; min: number; max: number }) {
  const stored = Number(useStored(key));
  const [dragging, setDragging] = useState<number | null>(null);
  // Where storage is blocked the choice still holds for this visit; it just isn't remembered.
  const [kept, setKept] = useState<number | null>(null);
  // The row the pane sits in: the pane never takes more than about half of it, so a width chosen on a wide
  // monitor can't squeeze the other pane to nothing in a narrow window.
  const [room, setRoom] = useState<number | null>(null);
  const self = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const row = self.current?.parentElement?.parentElement;
    if (!row) return;
    const watch = new ResizeObserver(() => setRoom(row.clientWidth));
    watch.observe(row);
    return () => watch.disconnect();
  }, []);
  const top = room ? Math.max(min, Math.min(max, Math.floor(room * 0.55))) : max;
  const clamp = (w: number) => Math.round(Math.min(top, Math.max(min, w)));
  const width = clamp(dragging ?? kept ?? (stored || initial));
  const start = useRef<{ x: number; w: number } | null>(null);
  const save = (w: number | null) => { if (!writeStored(key, w === null ? null : String(w))) setKept(w); else setKept(null); };

  const handle = (
    // A separator with a value is the accessible form of a resize handle: arrows move it, Home resets it.
    <div ref={self} role="separator" aria-orientation="vertical" aria-label="Resize the list" tabIndex={0}
      aria-valuemin={min} aria-valuemax={top} aria-valuenow={width} title="Drag to resize, double-click to reset"
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        start.current = { x: e.clientX, w: width };
        setDragging(width);
      }}
      onPointerMove={(e) => { if (start.current) setDragging(clamp(start.current.w + e.clientX - start.current.x)); }}
      onPointerUp={() => {
        if (start.current && dragging != null) save(clamp(dragging));
        start.current = null;
        setDragging(null);
      }}
      onPointerCancel={() => { start.current = null; setDragging(null); }}
      onDoubleClick={() => save(null)}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 64 : 16;
        const next = e.key === "ArrowLeft" ? width - step : e.key === "ArrowRight" ? width + step : e.key === "Home" ? null : undefined;
        if (next === undefined) return;
        e.preventDefault();
        save(next === null ? null : clamp(next));
      }}
      data-dragging={dragging != null || undefined}
      className="vt-splitter absolute inset-y-0 -right-1.5 z-10 hidden w-3 cursor-col-resize touch-none md:block" />
  );
  return { width, handle, dragging: dragging != null };
}

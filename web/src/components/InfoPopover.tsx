"use client";

import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { InfoIcon } from "./Icons";

/** A small "how is this worked out" note, opened from a button next to what it explains.
 * It is a disclosure rather than a dialog: the note comes right after its button
 * in reading order, so focus never has to move into it. */
export function InfoPopover({ label, children }: { label: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const onDown = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={open ? id : undefined}
        className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-muted transition hover:bg-sunken hover:text-ink">
        <InfoIcon size={14} /> {label}
      </button>
      {open && (
        <div id={id} role="region" aria-label={label}
          className="vt-pop absolute right-0 top-full z-30 mt-2 w-[min(26rem,calc(100vw-2.5rem))] rounded-xl border border-line bg-raised p-4 text-sm shadow-[var(--vt-shadow-pop)]">
          {children}
        </div>
      )}
    </div>
  );
}

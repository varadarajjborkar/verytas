"use client";

import { type ReactNode, useEffect, useRef } from "react";
import { CloseIcon } from "./Icons";

/** A side drawer for small screens: a modal dialog that takes focus, closes on
 * Escape or a tap outside, and hands focus back to whatever opened it. */
export function Drawer({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const panel = useRef<HTMLDivElement>(null);
  // Callers pass inline closures; the focus setup below must run once, not on every render.
  const close = useRef(onClose);
  useEffect(() => { close.current = onClose; }, [onClose]);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>("button, a[href], input, [tabindex]:not([tabindex='-1'])")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key !== "Tab" || !panel.current) return;
      const items = panel.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input, [tabindex]:not([tabindex='-1'])");
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-40">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-label={label}
        className="vt-pop absolute inset-y-3 left-3 w-[min(19rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <button type="button" onClick={onClose} aria-label={`Close ${label.toLowerCase()}`}
          className="absolute right-2 top-2.5 z-10 grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-sunken"><CloseIcon size={15} /></button>
        <div className="h-full pt-10">{children}</div>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ArrowLeftIcon, ChevronLeftIcon } from "./Icons";
import { HEADER_BACK } from "./ui";

/**
 * The way out of a detail view, the same size and place on every screen: a chevron just before the page
 * title when the page has one (where it goes is its tooltip and its accessible name), a labelled pill
 * inline otherwise. A link when it goes to a URL, a button when it closes local state.
 *
 * Once that spot scrolls out of sight, the same way back floats at the top of the content column, so leaving
 * a long piece never means scrolling up to the title first.
 */
export function BackButton({ label, href, onClick }: { label: string; href?: string; onClick?: () => void }) {
  // undefined on the server (the slot is only known in the browser), then the slot, or null for inline.
  const slot = useSyncExternalStore(noSubscription, () => document.getElementById(HEADER_BACK), () => undefined);
  const inline = useRef<HTMLElement | null>(null);
  // Where the column starts, measured when the button leaves the screen; null while it is in view.
  const [floating, setFloating] = useState<number | null>(null);

  useEffect(() => {
    const anchor = slot ?? inline.current;
    if (!anchor) return;
    // The header's chevron hangs in the margin; the floating pill lines up with the title it sat beside.
    const edge = () => Math.max(12, (slot ? anchor.nextElementSibling ?? anchor : anchor).getBoundingClientRect().left);
    let away = false;
    const seen = new IntersectionObserver((entries) => {
      away = !entries[entries.length - 1].isIntersecting;
      setFloating(away ? edge() : null);
    });
    // The column moves when the window is resized or the sidebar folds; keep the pill over it.
    const follow = () => { if (away) setFloating(edge()); };
    const column = new ResizeObserver(follow);
    column.observe(anchor.closest("main") ?? document.body);
    window.addEventListener("resize", follow);
    seen.observe(anchor);
    return () => { seen.disconnect(); column.disconnect(); window.removeEventListener("resize", follow); };
  }, [slot]);

  if (slot === undefined) return null;
  const name = `Back to ${label}`;
  const cls = slot
    ? "grid h-8 w-8 place-items-center rounded-full text-muted transition-colors hover:bg-sunken hover:text-ink"
    : "vt-btn vt-btn-quiet rounded-full pl-2.5 pr-3.5";
  const body = slot ? <ChevronLeftIcon size={20} strokeWidth={2.25} /> : <><ArrowLeftIcon size={16} />{label}</>;
  const make = (className: string, content: React.ReactNode, ref?: (el: HTMLElement | null) => void) => href
    ? <Link ref={ref} href={href} className={className} aria-label={name} title={name}>{content}</Link>
    : <button ref={ref} type="button" onClick={onClick} className={className} aria-label={name} title={name}>{content}</button>;
  const button = make(cls, body, slot ? undefined : (el) => { inline.current = el; });
  const pill = floating != null && createPortal(
    <div className="vt-pop fixed top-3 z-[45]" style={{ left: floating }}>
      {make("vt-btn h-9 rounded-full border-line-strong bg-[color-mix(in_srgb,var(--vt-raised)_88%,transparent)] pl-2.5 pr-3.5 shadow-[var(--vt-shadow-pop)] backdrop-blur",
        <><ArrowLeftIcon size={16} /><span className="max-w-[40vw] truncate">{label}</span></>)}
    </div>,
    document.body,
  );
  return <>{slot ? createPortal(button, slot) : button}{pill}</>;
}

const noSubscription = () => () => {};

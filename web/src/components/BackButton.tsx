"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ArrowLeftIcon, ChevronLeftIcon } from "./Icons";
import { HEADER_BACK } from "./ui";

/**
 * The way out of a detail view, the same size and place on every screen: a chevron just before the page
 * title when the page has one (where it goes is its tooltip and its accessible name), a labelled pill
 * inline otherwise. A link when it goes to a URL, a button when it closes local state.
 */
export function BackButton({ label, href, onClick }: { label: string; href?: string; onClick?: () => void }) {
  // undefined on the server (the slot is only known in the browser), then the slot, or null for inline.
  const slot = useSyncExternalStore(noSubscription, () => document.getElementById(HEADER_BACK), () => undefined);

  if (slot === undefined) return null;
  const name = `Back to ${label}`;
  const cls = slot
    ? "grid h-8 w-8 place-items-center rounded-full text-muted transition-colors hover:bg-sunken hover:text-ink"
    : "vt-btn vt-btn-quiet rounded-full pl-2.5 pr-3.5";
  const body = slot ? <ChevronLeftIcon size={20} strokeWidth={2.25} /> : <><ArrowLeftIcon size={16} />{label}</>;
  const button = href
    ? <Link href={href} className={cls} aria-label={name} title={name}>{body}</Link>
    : <button type="button" onClick={onClick} className={cls} aria-label={name} title={name}>{body}</button>;
  return slot ? createPortal(button, slot) : button;
}

const noSubscription = () => () => {};

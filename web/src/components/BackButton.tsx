"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ArrowLeftIcon } from "./Icons";
import { HEADER_BACK } from "./ui";

/**
 * The way out of a detail view, the same size and place on every screen: beside the page title when
 * the page has one, inline otherwise. A link when it goes to a URL, a button when it closes local state.
 */
export function BackButton({ label, href, onClick }: { label: string; href?: string; onClick?: () => void }) {
  // undefined on the server (the slot is only known in the browser), then the slot, or null for inline.
  const slot = useSyncExternalStore(noSubscription, () => document.getElementById(HEADER_BACK), () => undefined);

  const cls = "vt-btn vt-btn-quiet rounded-full pl-2.5 pr-3.5";
  const body = <><ArrowLeftIcon size={16} />{label}</>;
  const button = href
    ? <Link href={href} className={cls}>{body}</Link>
    : <button type="button" onClick={onClick} className={cls}>{body}</button>;
  if (slot === undefined) return null;
  return slot ? createPortal(button, slot) : button;
}

const noSubscription = () => () => {};

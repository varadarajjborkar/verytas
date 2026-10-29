"use client";

import Link from "next/link";
import { useEffect, useRef, useSyncExternalStore } from "react";
import { CONSENT_KEY, dropPreferences, useStored, writeStored } from "@/lib/stored";

const noop = () => () => {};

/**
 * The first visit's cookie question. There is no "reject all": what the site needs (signing in, the browser
 * id that keeps this visitor's Inki notes apart from others on a shared demo person, this answer) is kept
 * either way. The choice is only whether preferences (theme, layout, recent searches) outlive the visit.
 * Nothing here tracks anyone. The landing page asks the same question under the same key.
 */
export function CookieNotice() {
  const answered = useStored(CONSENT_KEY);
  // Not on the server render: a returning visitor would see it flash before storage is read.
  const ready = useSyncExternalStore(noop, () => true, () => false);
  const bar = useRef<HTMLElement>(null);
  const showing = ready && !answered;
  // While it is up, its height is a CSS variable: the review dock and toasts sit above it and the page gets as
  // much room at the foot, so nothing is left under the bar (globals.css, --vt-cookie-h).
  useEffect(() => {
    const el = bar.current;
    if (!showing || !el) return;
    const root = document.documentElement;
    const ro = new ResizeObserver(() => root.style.setProperty("--vt-cookie-h", `${el.offsetHeight}px`));
    ro.observe(el);
    return () => { ro.disconnect(); root.style.removeProperty("--vt-cookie-h"); };
  }, [showing]);
  if (!showing) return null;

  const choose = (v: "all" | "necessary") => {
    if (v === "necessary") dropPreferences();
    writeStored(CONSENT_KEY, v);
  };
  return (
    // A bar across the foot of the screen rather than a card: it reads as a site notice, not part of a page.
    <section ref={bar} role="region" aria-label="Cookies"
      className="fixed inset-x-0 bottom-0 z-[60] border-t border-line bg-raised/95 shadow-[0_-8px_24px_rgba(0,0,0,0.08)] backdrop-blur">
      <div className="mx-auto flex max-w-[1320px] flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:gap-6 md:px-10">
        <p className="min-w-0 flex-1 text-sm leading-6 text-muted">
          <b className="font-semibold text-ink">Cookies.</b> We keep what the site needs: your sign-in, a random id for
          this browser so what you tell Ask Inki stays yours on a shared demo account, and this choice.{" "}
          <b className="font-medium text-ink">Accept all</b> also remembers your theme, layout and recent searches.
          Nothing tracks you.{" "}
          <Link href="/privacy" className="text-accent underline-offset-2 hover:underline">Privacy</Link>
        </p>
        <div className="flex shrink-0 justify-end gap-2">
          <button type="button" onClick={() => choose("necessary")} className="vt-btn vt-btn-quiet vt-btn-sm">Necessary only</button>
          <button type="button" onClick={() => choose("all")} className="vt-btn vt-btn-primary vt-btn-sm">Accept all</button>
        </div>
      </div>
    </section>
  );
}

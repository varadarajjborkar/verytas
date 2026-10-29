"use client";

import { useSyncExternalStore } from "react";

// A localStorage value as an external store: every component (and every open
// tab) sees the same value, and server rendering falls back to `fallback`.
const EVENT = "vt-stored";

// The cookie notice's answer (components/CookieNotice.tsx). With "necessary", preferences (theme, layout,
// recent searches) still work but last only for this visit; the few keys the site needs are kept regardless.
export const CONSENT_KEY = "vt-consent";
const NEEDED = (key: string) => key === CONSENT_KEY || key.startsWith("vt-tour:") || key === "vt-chats";
// This visit's preferences while they may not be kept.
const visit = new Map<string, string | null>();

function raw(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // private mode or blocked storage
  }
}

/** Whether a key may be written to storage under the visitor's choice. */
export const mayKeep = (key: string) => NEEDED(key) || raw(CONSENT_KEY) !== "necessary";

/** The value as this visit sees it: a preference held for the visit, else what storage has. */
export function readStored(key: string): string | null {
  return visit.has(key) ? visit.get(key)! : raw(key);
}

/** True when the value was kept in storage. Either way this visit sees it: with storage blocked (Safari's
 * private mode) or a preference under "necessary", it lives in memory until the tab closes. */
export function writeStored(key: string, value: string | null): boolean {
  let kept = false;
  try {
    if (mayKeep(key)) {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
      visit.delete(key);
      kept = true;
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    // Storage blocked: held below for this visit.
  }
  if (!kept) visit.set(key, value);
  // Preferences held for the visit become kept ones once the visitor accepts them.
  if (key === CONSENT_KEY && value === "all" && kept) {
    for (const [k, v] of [...visit]) {
      try {
        if (v === null) localStorage.removeItem(k);
        else localStorage.setItem(k, v);
        visit.delete(k);
      } catch {
        break;
      }
    }
  }
  window.dispatchEvent(new Event(EVENT));
  return kept;
}

/** "Necessary only" also clears preferences kept before the choice; they carry on for this visit. */
export function dropPreferences() {
  try {
    for (const key of Object.keys(localStorage)) {
      if (!key.startsWith("vt-") || NEEDED(key)) continue;
      visit.set(key, localStorage.getItem(key));
      localStorage.removeItem(key);
    }
  } catch {
    // Nothing kept, or nothing to clear.
  }
}

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener(EVENT, cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener(EVENT, cb);
  };
}

export function useStored(key: string): string | null {
  return useSyncExternalStore(subscribe, () => readStored(key), () => null);
}

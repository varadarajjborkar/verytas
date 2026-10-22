"use client";

import { useSyncExternalStore } from "react";

// A localStorage value as an external store: every component (and every open
// tab) sees the same value, and server rendering falls back to `fallback`.
const EVENT = "vt-stored";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // private mode or blocked storage
  }
}

export function writeStored(key: string, value: string | null): boolean {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
    window.dispatchEvent(new Event(EVENT));
    return true;
  } catch {
    return false;
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
  return useSyncExternalStore(subscribe, () => read(key), () => null);
}

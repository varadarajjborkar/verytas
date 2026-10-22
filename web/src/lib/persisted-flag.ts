"use client";

import { useCallback, useSyncExternalStore } from "react";

// A per-browser on/off preference (a collapsed panel, say). It is a convenience
// only: blocked storage falls back to the default, and every open tab updates.

const listeners = new Set<() => void>();
// This visit's choices, so a toggle still works when storage is blocked.
const memory = new Map<string, boolean>();

function read(key: string, fallback: boolean): boolean {
  const known = memory.get(key);
  if (known !== undefined) return known;
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : raw === "1";
  } catch {
    return fallback;
  }
}

function subscribe(onChange: () => void) {
  // Another tab changed it: its stored value now wins over this tab's memory.
  const onStorage = (e: StorageEvent) => {
    if (e.key) memory.delete(e.key);
    onChange();
  };
  listeners.add(onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onStorage);
  };
}

export function usePersistedFlag(key: string, fallback: boolean): [boolean, (value: boolean) => void] {
  // The server render uses the default; the saved value takes over on hydration.
  const value = useSyncExternalStore(subscribe, () => read(key, fallback), () => fallback);
  const set = useCallback((next: boolean) => {
    memory.set(key, next);
    try {
      localStorage.setItem(key, next ? "1" : "0");
    } catch {
      // Not remembered past this visit.
    }
    listeners.forEach((l) => l());
  }, [key]);
  return [value, set];
}

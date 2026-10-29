"use client";

import { useCallback, useSyncExternalStore } from "react";
import { readStored, writeStored } from "./stored";

// A per-browser on/off preference (a collapsed panel, say). It is a convenience
// only: blocked storage falls back to the default, and every open tab updates.

const listeners = new Set<() => void>();
// This visit's choices, so a toggle still works when storage is blocked.
const memory = new Map<string, boolean>();

function read(key: string, fallback: boolean): boolean {
  const known = memory.get(key);
  if (known !== undefined) return known;
  // Through stored.ts, so a flag held for the visit under "necessary" (or with storage blocked) still reads back.
  const raw = readStored(key);
  return raw === null ? fallback : raw === "1";
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
    // Through stored.ts, which keeps it, or holds it for the visit under "necessary" so a later "Accept all"
    // keeps this value and not an older one.
    writeStored(key, next ? "1" : "0");
    listeners.forEach((l) => l());
  }, [key]);
  return [value, set];
}

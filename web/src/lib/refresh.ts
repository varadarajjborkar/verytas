"use client";

import { useEffect } from "react";

// One page-wide "fetch it again". Server-rendered data comes back through router.refresh(); lists a
// client component fetched itself listen for this event, so a single Refresh button reaches both.
const EVENT = "vt:refresh";

export function requestRefresh() {
  window.dispatchEvent(new Event(EVENT));
}

export function useOnRefresh(load: () => unknown) {
  useEffect(() => {
    const run = () => void load();
    window.addEventListener(EVENT, run);
    return () => window.removeEventListener(EVENT, run);
  }, [load]);
}

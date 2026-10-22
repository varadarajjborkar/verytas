"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { requestRefresh } from "@/lib/refresh";
import { RefreshIcon } from "./Icons";

/** Fetches the page's data again without a reload: filters, open panels and scroll position stay put. */
export function RefreshButton({ onRefresh, compact = false }: { onRefresh?: () => unknown; compact?: boolean }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [spinning, setSpinning] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const busy = pending || spinning;

  function refresh() {
    // Ignored rather than disabled while busy, so keyboard focus stays on the button.
    if (busy) return;
    // The spin lasts long enough to be seen even when the answer is instant, so a click never looks ignored.
    setSpinning(true);
    timer.current = setTimeout(() => setSpinning(false), 700);
    if (onRefresh) void onRefresh();
    else requestRefresh();
    startTransition(() => router.refresh());
  }

  return (
    <button type="button" onClick={refresh} aria-busy={busy} title="Fetch the latest"
      className={`vt-btn vt-btn-quiet ${compact ? "h-8 px-2.5 text-xs" : "h-9 text-sm"}`}>
      <RefreshIcon size={compact ? 14 : 15} className={busy ? "animate-spin" : undefined} />
      <span aria-live="polite" className={compact ? "sr-only" : undefined}>{busy ? "Refreshing" : "Refresh"}</span>
    </button>
  );
}

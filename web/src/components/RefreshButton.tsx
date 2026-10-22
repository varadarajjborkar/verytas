"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { requestRefresh } from "@/lib/refresh";
import { RefreshIcon } from "./Icons";

/** Fetches the page's data again without a reload: filters, open panels and scroll position stay put. */
export function RefreshButton({ onRefresh, compact = false }: { onRefresh?: () => unknown; compact?: boolean }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [spinning, setSpinning] = useState(false);
  const busy = pending || spinning;

  function refresh() {
    // The spin lasts long enough to be seen even when the answer is instant, so a click never looks ignored.
    setSpinning(true);
    setTimeout(() => setSpinning(false), 700);
    if (onRefresh) void onRefresh();
    else requestRefresh();
    startTransition(() => router.refresh());
  }

  return (
    <button type="button" onClick={refresh} disabled={busy} aria-label="Refresh" title="Fetch the latest"
      className={`vt-btn vt-btn-quiet ${compact ? "h-8 px-2.5 text-xs" : "h-9 text-sm"}`}>
      <RefreshIcon size={compact ? 14 : 15} className={busy ? "animate-spin" : undefined} />
      <span className={compact ? "sr-only" : undefined}>{busy ? "Refreshing" : "Refresh"}</span>
    </button>
  );
}

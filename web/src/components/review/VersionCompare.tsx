"use client";

import { useMemo, useState } from "react";
import { diffStats, diffText } from "@/lib/diff";
import { relativeTime } from "@/lib/review-client";
import type { ContentDetail } from "@/lib/types";

type Version = ContentDetail["versions"][number];

/** Track changes between any two versions: removed words struck in red, added ones in green. */
export function VersionCompare({ versions }: { versions: Version[] }) {
  const [from, setFrom] = useState(versions.length - 2);
  const [to, setTo] = useState(versions.length - 1);
  const a = versions[Math.min(from, to)];
  const b = versions[Math.max(from, to)];
  const chunks = useMemo(() => (a && b ? diffText(a.body, b.body) : []), [a, b]);
  const stats = diffStats(chunks);
  if (!a || !b) return null;

  const pick = (value: number, set: (n: number) => void, label: string) => (
    <select value={value} onChange={(e) => set(Number(e.target.value))} aria-label={label}
      className="vt-input w-auto py-1 pl-2 pr-7 text-xs">
      {versions.map((v, i) => (
        <option key={v.id} value={i}>v{v.version_no} · {relativeTime(v.created_at)}</option>
      ))}
    </select>
  );
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted">
        {pick(from, setFrom, "Compare from version")}
        <span aria-hidden>to</span>
        {pick(to, setTo, "Compare to version")}
        <span className="ml-auto tabular-nums">
          <span className="text-[var(--vt-ok)]">+{stats.added}</span>{" "}
          <span className="text-[var(--vt-blocker)]">&minus;{stats.removed}</span> words
        </span>
      </div>
      {a.id === b.id ? (
        <p className="text-sm text-muted">Pick two different versions.</p>
      ) : stats.added + stats.removed === 0 ? (
        <p className="text-sm text-muted">The text is the same in both versions.</p>
      ) : (
        <p className="whitespace-pre-wrap break-words text-[15px] leading-7" aria-label={`Changes from v${a.version_no} to v${b.version_no}`}>
          {chunks.map((c, i) => c.op === "same" ? <span key={i}>{c.text}</span>
            : c.op === "del"
              ? <del key={i} className="rounded-[3px] bg-[var(--vt-blocker-bg)] text-[var(--vt-blocker)] decoration-1">{c.text}</del>
              : <ins key={i} className="rounded-[3px] bg-[var(--vt-ok-bg)] text-[var(--vt-ok)] no-underline">{c.text}</ins>)}
        </p>
      )}
    </div>
  );
}

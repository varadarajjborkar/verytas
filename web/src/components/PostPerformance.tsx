"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/Toaster";
import { importResults, performanceReport } from "@/lib/review-client";
import type { PerformanceReport } from "@/lib/types";

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const pp = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}`;

/**
 * How live posts did, by rule: engagement for the posts that ran into a rule against the ones that didn't.
 * A row says nothing until both sides have enough posts, and then gives a range, not a single number, so a
 * handful of posts can't read as a verdict. Advice for the brand team; it never changes a rule.
 */
export function PostPerformance({ canImport }: { canImport: boolean }) {
  const [report, setReport] = useState<PerformanceReport | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const toast = useToast();

  const load = useCallback(() => performanceReport().then((r) => { setReport(r); setFailed(null); })
    .catch((e: Error) => setFailed(e.message)), []);
  useEffect(() => { void load(); }, [load]);

  const importSheet = async (file: File) => {
    if (file.size > 500_000) { toast({ kind: "error", title: "That sheet is too big", detail: "Up to 500 KB, about 2,000 rows." }); return; }
    setBusy(true);
    try {
      const res = await importResults(await file.text());
      toast({
        kind: res.updated ? "success" : "warning",
        title: `${res.updated} post${res.updated === 1 ? "" : "s"} updated`,
        detail: res.skipped.length ? `${res.skipped.length} row${res.skipped.length === 1 ? "" : "s"} skipped: ${res.skipped[0].reason}` : "Every row matched a recorded link.",
      });
      void load();
    } catch (e) {
      toast({ kind: "error", title: "The sheet wasn't imported", detail: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  if (failed) return null;
  const ready = report?.rules.filter((r) => r.difference_90) ?? [];
  const waiting = report?.rules.filter((r) => !r.difference_90) ?? [];

  return (
    <section aria-labelledby="perf-title" className="vt-card mt-6 p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="perf-title" className="text-base font-semibold">How live posts did</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Engagement for approved posts that ran into a rule, against those that didn&apos;t. Links and numbers come
            from creators and the brand team; nothing is read from the platforms.
          </p>
        </div>
        {canImport && (
          <>
            <input ref={picker} type="file" accept=".csv,text/csv" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void importSheet(f); }} />
            <button type="button" onClick={() => picker.current?.click()} disabled={busy} className="vt-btn h-8 text-xs"
              title="A CSV with a url column and any of reach, views, likes, comments, shares, saves">
              {busy ? "Importing…" : "Import numbers (CSV)"}
            </button>
          </>
        )}
      </div>

      {!report ? (
        <div aria-busy="true" className="mt-4 h-16 animate-pulse rounded-lg bg-sunken" />
      ) : (
        <>
          <dl className="mt-4 flex flex-wrap gap-2 text-sm">
            {[["Approved pieces", report.live_pieces], ["With a live link", report.with_link], ["With numbers", report.with_numbers]].map(([k, v]) => (
              <div key={k} className="rounded-lg bg-sunken px-3 py-1.5">
                <dt className="text-[11px] text-muted">{k}</dt>
                <dd className="font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>

          {report.with_numbers === 0 ? (
            <p className="mt-4 text-sm text-muted">
              No numbers yet. When a piece goes live, its creator adds the link on the piece, with the numbers if they have
              them; the brand team can import a sheet of numbers by link.
            </p>
          ) : (
            <>
              {ready.length > 0 && (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[36rem] text-sm">
                    <thead>
                      <tr className="text-left text-xs text-muted">
                        <th className="py-2 pr-3 font-medium">Rule</th>
                        <th className="py-2 pr-3 font-medium">Ran into it</th>
                        <th className="py-2 pr-3 font-medium">Didn&apos;t</th>
                        <th className="py-2 pr-3 font-medium" title="90% range of the difference in median engagement">Difference</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ready.map((r) => {
                        const [lo, hi] = r.difference_90!;
                        const verdict = hi < 0 ? "did worse" : lo > 0 ? "did better" : "no clear difference";
                        return (
                          <tr key={r.rule_id} className="border-t border-line align-top">
                            <td className="py-2 pr-3"><span className="font-medium">{r.title}</span> <span className="text-xs text-subtle">{r.code}</span></td>
                            <td className="py-2 pr-3 tabular-nums">{pct(r.median_needed!)} <span className="text-xs text-subtle">of {r.needed}</span></td>
                            <td className="py-2 pr-3 tabular-nums">{pct(r.median_clean!)} <span className="text-xs text-subtle">of {r.clean}</span></td>
                            <td className="py-2 pr-3">
                              <span className="tabular-nums">{pp(lo)} to {pp(hi)} points</span>
                              <span className={`ml-2 text-xs ${hi < 0 ? "text-[var(--vt-warning)]" : lo > 0 ? "text-[var(--vt-ok)]" : "text-subtle"}`}>{verdict}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {waiting.length > 0 && (
                <p className="mt-3 text-xs text-subtle">
                  Not enough posts yet for {waiting.length} rule{waiting.length === 1 ? "" : "s"}: a comparison needs
                  {" "}{report.min_posts} live posts with numbers on each side.
                </p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

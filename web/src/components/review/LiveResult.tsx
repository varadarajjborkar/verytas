"use client";

import { useEffect, useState } from "react";
import { ExternalIcon } from "@/components/Icons";
import { useToast } from "@/components/Toaster";
import { getResult, removeResult, saveResult } from "@/lib/review-client";
import type { PostMetrics, PostResult } from "@/lib/types";
import { shownError } from "@/lib/errors";

const FIELDS: { key: keyof PostMetrics; label: string }[] = [
  { key: "reach", label: "Reach" }, { key: "views", label: "Views" }, { key: "likes", label: "Likes" },
  { key: "comments", label: "Comments" }, { key: "shares", label: "Shares" }, { key: "saves", label: "Saves" },
];
const PLATFORM: Record<string, string> = {
  instagram: "Instagram", youtube: "YouTube", x: "X", linkedin: "LinkedIn", facebook: "Facebook",
  tiktok: "TikTok", threads: "Threads", pinterest: "Pinterest", other: "Live post",
};
const number = new Intl.NumberFormat("en-IN");

/**
 * Once a piece is approved: where it went live, and how it did. The creator (or the brand team) pastes the
 * link and, if they have them, the numbers the platform shows; nothing is fetched from the platform. The
 * brand team reads these together in Guideline health, per rule.
 */
export function LiveResult({ contentId, canRecord }: { contentId: number; canRecord: boolean }) {
  const [result, setResult] = useState<PostResult | null | undefined>(undefined);
  // A failed load isn't "no link yet": showing the empty form then would invite overwriting a real one.
  const [loadFailed, setLoadFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState("");
  const [postedOn, setPostedOn] = useState("");
  const [numbers, setNumbers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  useEffect(() => {
    let live = true;
    getResult(contentId).then((r) => { if (live) setResult(r); }).catch(() => { if (live) setLoadFailed(true); });
    return () => { live = false; };
  }, [contentId]);

  const open = () => {
    setUrl(result?.url ?? "");
    setPostedOn(result?.posted_on ?? "");
    setNumbers(Object.fromEntries(FIELDS.map((f) => [f.key, result?.metrics[f.key]?.toString() ?? ""])));
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    if (busy) return;
    // Numbers the form has no field for (watch time from an imported sheet) carry over; PUT replaces the set.
    const shown = new Set<string>(FIELDS.map((f) => f.key));
    const metrics: PostMetrics = Object.fromEntries(
      Object.entries(result?.metrics ?? {}).filter(([k]) => !shown.has(k))) as PostMetrics;
    for (const f of FIELDS) {
      const raw = (numbers[f.key] ?? "").replace(/[,\s]/g, "");
      if (!raw) continue;
      const n = Number(raw);
      if (!Number.isInteger(n) || n < 0) { setError(`${f.label} should be a whole number.`); return; }
      metrics[f.key] = n;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = await saveResult(contentId, { url: url.trim(), posted_on: postedOn || null, metrics });
      setResult(saved);
      setEditing(false);
      toast({ kind: "success", title: "Live link saved", detail: saved.engagement_rate != null ? "The numbers count toward how rules perform." : "Add numbers any time, here or from a sheet." });
    } catch (e) {
      setError(shownError(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Remove the live link and its numbers from this piece?")) return;
    try { await removeResult(contentId); setResult(null); }
    catch (e) { toast({ kind: "error", title: "Couldn't remove it", detail: shownError(e) }); }
  };

  if (loadFailed) {
    return (
      <section aria-label="Live post" className="vt-card mt-4 p-4 text-sm text-muted md:p-5">
        The live post&apos;s link couldn&apos;t be loaded just now. Reload the page to see or change it.
      </section>
    );
  }
  if (result === undefined) return null;
  if (!result && !canRecord) return null;

  return (
    <section aria-label="Live post" className="vt-card mt-4 p-4 md:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Live post</h3>
        {result && !editing && canRecord && (
          <div className="flex gap-1">
            <button type="button" onClick={open} className="vt-btn vt-btn-quiet h-7 px-2 text-xs">Edit</button>
            <button type="button" onClick={remove} className="vt-btn vt-btn-quiet h-7 px-2 text-xs">Remove</button>
          </div>
        )}
      </div>

      {!editing && !result && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted">Posted it? Add the link, and the numbers if you have them, so the brand team can see how it did.</p>
          <button type="button" onClick={open} className="vt-btn h-8 text-xs">Add the live link</button>
        </div>
      )}

      {!editing && result && (
        <div className="mt-2 flex flex-col gap-3">
          <a href={result.url} target="_blank" rel="noopener noreferrer nofollow"
            className="flex min-w-0 items-center gap-2 text-sm font-medium text-accent hover:underline">
            <span className="shrink-0">{PLATFORM[result.platform] ?? "Live post"}</span>
            <span className="truncate text-muted">{result.url.replace(/^https:\/\//, "")}</span>
            <ExternalIcon size={13} className="shrink-0" />
          </a>
          {Object.keys(result.metrics).length > 0 ? (
            <dl className="flex flex-wrap gap-2">
              {FIELDS.filter((f) => result.metrics[f.key] != null).map((f) => (
                <div key={f.key} className="rounded-lg bg-sunken px-3 py-1.5">
                  <dt className="text-[11px] text-muted">{f.label}</dt>
                  <dd className="text-sm font-semibold tabular-nums">{number.format(result.metrics[f.key]!)}</dd>
                </div>
              ))}
              {result.engagement_rate != null && (
                <div className="rounded-lg bg-accent/10 px-3 py-1.5" title="Likes, comments, shares and saves per person reached (or per view)">
                  <dt className="text-[11px] text-muted">Engagement</dt>
                  <dd className="text-sm font-semibold tabular-nums">{(result.engagement_rate * 100).toFixed(1)}%</dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="text-xs text-subtle">No numbers yet.{canRecord ? " Add them with Edit, or the brand team can import a sheet." : ""}</p>
          )}
          <p className="text-[11px] text-subtle">
            {result.posted_on ? `Posted ${new Date(`${result.posted_on}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} · ` : ""}
            {result.source === "csv" ? "Numbers from an imported sheet" : "Entered by hand"}. Nothing is read from the platform.
          </p>
        </div>
      )}

      {editing && (
        <form className="mt-3 flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <label className="flex flex-col gap-1 text-xs font-medium">
              Link to the live post
              <input value={url} onChange={(e) => setUrl(e.target.value)} type="url" inputMode="url" required maxLength={500}
                placeholder="https://www.instagram.com/p/..." className="vt-input text-sm font-normal" autoFocus />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium">
              Posted on <span className="sr-only">(optional)</span>
              <input value={postedOn} onChange={(e) => setPostedOn(e.target.value)} type="date" className="vt-input text-sm font-normal" />
            </label>
          </div>
          <fieldset className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <legend className="mb-1 text-xs font-medium">Numbers <span className="font-normal text-subtle">optional, as the platform shows them</span></legend>
            {FIELDS.map((f) => (
              <label key={f.key} className="flex flex-col gap-1 text-[11px] text-muted">
                {f.label}
                <input value={numbers[f.key] ?? ""} onChange={(e) => setNumbers({ ...numbers, [f.key]: e.target.value })}
                  inputMode="numeric" maxLength={16} className="vt-input text-sm tabular-nums text-ink" />
              </label>
            ))}
          </fieldset>
          {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !url.trim()} className="vt-btn vt-btn-primary h-8 text-xs">{busy ? "Saving…" : "Save"}</button>
            <button type="button" onClick={() => setEditing(false)} className="vt-btn vt-btn-quiet h-8 text-xs">Cancel</button>
          </div>
        </form>
      )}
    </section>
  );
}

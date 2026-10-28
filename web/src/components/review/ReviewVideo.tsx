"use client";

import { useEffect, useRef, useState } from "react";
import { addPinnedComment, versionVideoUrl } from "@/lib/review-client";
import type { Finding, Level, PinnedComment } from "@/lib/types";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
const DOT: Record<Level, string> = {
  blocker: "bg-[var(--vt-blocker)]",
  warning: "bg-[var(--vt-warning)]",
  advisory: "bg-[var(--vt-advisory)]",
};
/** A press that moves less than this is a seek; more is a range being selected. */
const DRAG_PX = 4;

export const clock = (s: number) => {
  const t = Math.max(0, Math.floor(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

/**
 * One attached video as the review sees it: findings sit on the timeline where they happen, and picking
 * one (here or in the issue list) jumps to its moment. Dragging along the timeline selects a stretch to
 * comment on, so feedback lands on the exact seconds instead of "around the middle".
 *
 * Shown in place only: no download, no picture in picture, no casting, and no context menu. That stops
 * the casual save, not a determined screen recorder, and is meant to.
 */
export function ReviewVideo({ contentId, versionId, video, findings, comments, active, onSelect, onPinned, canComment }: {
  contentId: number;
  versionId: number;
  video: { id: string; name: string | null };
  findings: Finding[];
  comments: PinnedComment[];
  active: number | null;
  onSelect: (id: number) => void;
  onPinned: () => void;
  canComment: boolean;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const press = useRef<{ x: number; at: number; dragging: boolean } | null>(null);
  // A seek asked for before the length is known (a finding picked while the video loads) waits for it.
  const pending = useRef<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [now, setNow] = useState(0);
  const [length, setLength] = useState(0);
  const [rate, setRate] = useState(1);
  const [muted, setMuted] = useState(false);
  const [failed, setFailed] = useState(false);
  const [range, setRange] = useState<[number, number] | null>(null);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const key = `vid:${video.id}`;
  const moments = findings.filter((f) => f.locator?.video === key && Array.isArray(f.locator.time));
  const pinned = comments.filter((c) => c.media_id === video.id && c.time_start != null);

  // Picking a finding in the issue list brings its moment up here.
  useEffect(() => {
    const f = moments.find((m) => m.id === active);
    const v = ref.current;
    if (f && v && Number.isFinite(f.locator!.time![0])) {
      v.pause();
      if (Number.isFinite(v.duration) && v.duration > 0) v.currentTime = Math.min(v.duration, f.locator!.time![0]);
      else pending.current = f.locator!.time![0];
    }
    // Only a change of the picked finding should seek; new findings arriving must not move the playhead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  const at = (clientX: number) => {
    const box = track.current?.getBoundingClientRect();
    if (!box || !length) return 0;
    return Math.min(length, Math.max(0, ((clientX - box.left) / box.width) * length));
  };
  const seek = (t: number) => {
    const v = ref.current;
    if (!v) return;
    if (!length) { pending.current = Math.max(0, t); return; }
    v.currentTime = Math.min(length, Math.max(0, t));
  };
  // Some recordings (WebM from a browser) report an unknown length until they are read to the end; asking
  // for a far point makes the browser work it out, and durationchange then brings the real one.
  const learnLength = (v: HTMLVideoElement) => {
    if (Number.isFinite(v.duration) && v.duration > 0) {
      setLength(v.duration);
      if (pending.current != null) { v.currentTime = Math.min(v.duration, pending.current); pending.current = null; }
    } else if (v.duration === Infinity) {
      v.currentTime = Number.MAX_SAFE_INTEGER;
    }
  };
  const pct = (t: number) => `${length ? (Math.min(t, length) / length) * 100 : 0}%`;

  const toggle = () => {
    const v = ref.current;
    if (!v) return;
    if (v.paused) v.play().catch(() => setError("This video can't be played here."));
    else v.pause();
  };
  const speed = (r: number) => { setRate(r); if (ref.current) ref.current.playbackRate = r; };

  const onDown = (e: React.PointerEvent) => {
    if (!length || e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    press.current = { x: e.clientX, at: at(e.clientX), dragging: false };
  };
  const onMove = (e: React.PointerEvent) => {
    const p = press.current;
    if (!p) return;
    if (!p.dragging && Math.abs(e.clientX - p.x) < DRAG_PX) return;
    p.dragging = true;
    const t = at(e.clientX);
    if (canComment) setRange([Math.min(p.at, t), Math.max(p.at, t)]);
    else seek(t);
  };
  const onUp = (e: React.PointerEvent) => {
    const p = press.current;
    press.current = null;
    if (!p) return;
    if (!p.dragging || !canComment) { if (!p.dragging) seek(p.at); return; }
    const t = at(e.clientX);
    setRange([Math.min(p.at, t), Math.max(p.at, t)]);
    ref.current?.pause();
    seek(Math.min(p.at, t));
  };
  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 1 : 5;
    if (e.key === "ArrowRight") { e.preventDefault(); seek(now + step); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); seek(now - step); }
    else if (e.key === "Home") { e.preventDefault(); seek(0); }
    else if (e.key === "End") { e.preventDefault(); seek(length); }
    else if (e.key === " " || e.key === "k") { e.preventDefault(); toggle(); }
  };

  const post = async () => {
    if (!range || !note.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const [a, b] = range;
      await addPinnedComment(contentId, { body: note.trim(), version_id: versionId, media_id: video.id,
        time_start: Math.round(a * 10) / 10, time_end: b - a >= 0.5 ? Math.round(b * 10) / 10 : undefined });
      setNote("");
      setRange(null);
      onPinned();
    } catch (err) {
      setError((err as Error).message || "The comment wasn't saved.");
    } finally {
      setSaving(false);
    }
  };

  const shown = pinned.find((c) => c.id === open);
  return (
    <figure className="flex flex-col gap-2">
      <div className="group relative overflow-hidden rounded-lg border border-line bg-black">
        {failed ? (
          <p className="px-4 py-16 text-center text-xs text-white/70">This video couldn&apos;t be loaded.</p>
        ) : (
          <video ref={ref} src={versionVideoUrl(contentId, versionId, video.id)} preload="metadata" playsInline
            controlsList="nodownload noremoteplayback noplaybackrate" disablePictureInPicture disableRemotePlayback
            onContextMenu={(e) => e.preventDefault()} onClick={toggle}
            onLoadedMetadata={(e) => learnLength(e.currentTarget)}
            onDurationChange={(e) => {
              const v = e.currentTarget;
              // The far seek above found the end: take the length and come back to the start.
              if (Number.isFinite(v.duration) && v.duration > 0 && !length) { learnLength(v); if (pending.current == null && v.currentTime > 0) v.currentTime = 0; }
            }}
            onTimeUpdate={(e) => setNow(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.currentTime : 0)}
            onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
            onError={() => setFailed(true)}
            aria-label={video.name ? `Video: ${video.name}` : "Attached video"}
            className="block max-h-[70vh] w-full cursor-pointer bg-black object-contain" />
        )}
      </div>

      {!failed && (
        <div className="flex flex-col gap-2">
          {/* The timeline: findings as coloured marks, pinned comments as dots above, a dragged range shaded. */}
          <div className="flex flex-col">
            {/* Pinned comments, as dots in a row of their own above the line, each a full size tap target. */}
            {pinned.length > 0 && (
              <div className="relative h-6">
                {pinned.map((c) => (
                  <button key={c.id} type="button" onClick={() => { setOpen(open === c.id ? null : c.id); seek(c.time_start!); }}
                    aria-label={`Comment at ${clock(c.time_start!)}: ${c.body}`} aria-pressed={open === c.id}
                    className="group absolute top-0 flex h-6 w-6 -translate-x-1/2 items-center justify-center"
                    style={{ left: pct(c.time_start!) }}>
                    <span className={`h-2.5 w-2.5 rounded-full border-2 border-surface bg-accent transition group-hover:scale-125 ${open === c.id ? "scale-125 ring-2 ring-accent/40" : ""}`} />
                  </button>
                ))}
              </div>
            )}
            <div className="relative h-8">
              {/* The slider is only the line. Marks sit over it as their own buttons, so their keys stay theirs. */}
              <div ref={track} role="slider" tabIndex={0} aria-label="Video position" aria-valuemin={0}
                aria-valuemax={Math.round(length)} aria-valuenow={Math.round(now)} aria-valuetext={`${clock(now)} of ${clock(length)}`}
                onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => { press.current = null; }}
                onKeyDown={onKey}
                className="absolute inset-0 cursor-pointer touch-none select-none rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent/50">
                <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-sunken" />
                <div className="absolute left-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-accent/60" style={{ width: pct(now) }} />
                {range && (
                  <div className="absolute inset-y-1 rounded bg-accent/20 ring-1 ring-accent/60"
                    style={{ left: pct(range[0]), width: `calc(${pct(range[1] - range[0])} + 2px)` }} />
                )}
                <div className="pointer-events-none absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink" style={{ left: pct(now) }} />
              </div>
              <div className="pointer-events-none absolute inset-0">
                {moments.map((f) => {
                  const [t0, t1] = f.locator!.time!;
                  return (
                    <button key={f.id} type="button" title={`${clock(t0)} ${f.title}`}
                      aria-label={`${f.title} at ${clock(t0)}: show this issue`} aria-pressed={active === f.id}
                      onClick={() => { seek(t0); ref.current?.pause(); onSelect(f.id); }}
                      className="group pointer-events-auto absolute inset-y-0 flex items-center justify-center"
                      // The bar is the finding's stretch (6px at least); the button is 5px wider each side, 16px at least.
                      style={{ left: `calc(${pct(t0)} - 5px)`, width: `max(16px, calc(${pct(Math.max(0, t1 - t0))} + 10px))` }}>
                      <span className={`h-4 rounded-sm ${DOT[f.level]} transition ${
                        active === f.id ? "ring-2 ring-accent ring-offset-1 ring-offset-surface" : "opacity-85 group-hover:opacity-100"}`}
                        style={{ width: "max(6px, calc(100% - 10px))" }} />
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {error && !range && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-surface transition hover:opacity-85">
              {playing ? (
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden><rect x="3" y="2" width="3.5" height="12" rx="1" fill="currentColor" /><rect x="9.5" y="2" width="3.5" height="12" rx="1" fill="currentColor" /></svg>
              ) : (
                <svg viewBox="0 0 16 16" className="ml-0.5 h-3.5 w-3.5" aria-hidden><path d="M4 2.5v11a.8.8 0 0 0 1.2.7l9-5.5a.8.8 0 0 0 0-1.4l-9-5.5A.8.8 0 0 0 4 2.5Z" fill="currentColor" /></svg>
              )}
            </button>
            <span className="tabular-nums text-muted">{clock(now)} / {clock(length)}</span>
            <label className="ml-auto flex items-center gap-1 text-muted">
              Speed
              <select value={rate} onChange={(e) => speed(Number(e.target.value))} className="vt-input h-8 w-auto py-0 pl-2 pr-7 text-xs">
                {SPEEDS.map((s) => <option key={s} value={s}>{s}x</option>)}
              </select>
            </label>
            <button type="button" onClick={() => { const m = !muted; setMuted(m); if (ref.current) ref.current.muted = m; }}
              aria-pressed={muted} className="vt-btn vt-btn-quiet h-8 px-2 text-xs">{muted ? "Unmute" : "Mute"}</button>
            {canComment && !range && (
              <button type="button" onClick={() => { ref.current?.pause(); setRange([now, now]); }}
                className="vt-btn h-8 px-3 text-xs">Comment at {clock(now)}</button>
            )}
          </div>
          {moments.length > 0 && !range && (
            <p className="text-xs text-subtle">
              {moments.length} issue{moments.length === 1 ? "" : "s"} on the timeline. Pick a mark to jump to it{canComment ? "; drag along the timeline to comment on a stretch" : ""}.
            </p>
          )}

          {shown && (
            <p className="rounded-lg border border-line bg-sunken px-3 py-2 text-xs">
              <span className="font-medium tabular-nums">{clock(shown.time_start!)}{shown.time_end != null ? ` to ${clock(shown.time_end)}` : ""}</span>{" "}
              {shown.body}
            </p>
          )}

          {range && canComment && (
            <div className="flex flex-col gap-2 rounded-lg border border-accent/40 bg-accent/5 p-3">
              <p className="text-xs font-medium">
                {range[1] - range[0] >= 0.5 ? `Comment on ${clock(range[0])} to ${clock(range[1])}` : `Comment at ${clock(range[0])}`}
              </p>
              <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={5000} rows={2} autoFocus
                aria-label="Comment on this moment" placeholder="What should change here?"
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) post(); }}
                className="vt-input resize-y text-sm" />
              {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
              <div className="flex gap-2">
                <button type="button" onClick={post} disabled={saving || !note.trim()} className="vt-btn vt-btn-primary h-8 text-xs">
                  {saving ? "Saving…" : "Post comment"}
                </button>
                <button type="button" onClick={() => { setRange(null); setError(null); }} className="vt-btn vt-btn-quiet h-8 text-xs">Cancel</button>
              </div>
            </div>
          )}
        </div>
      )}
      <figcaption className="text-xs text-muted">
        <span className="font-medium text-ink">{video.name || video.id}</span>
        {moments.length > 0 && <span className="text-subtle"> · {moments.length} issue{moments.length === 1 ? "" : "s"}</span>}
        {pinned.length > 0 && <span className="text-subtle"> · {pinned.length} comment{pinned.length === 1 ? "" : "s"}</span>}
      </figcaption>
    </figure>
  );
}

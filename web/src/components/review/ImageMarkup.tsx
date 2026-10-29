"use client";

import { useRef, useState } from "react";
import { addPinnedComment } from "@/lib/review-client";
import type { Mark, PinnedComment } from "@/lib/types";
import { shownError } from "@/lib/errors";

/** The server's limits, so a drawing is refused here, with a reason, rather than by a 422. */
const MAX_MARKS = 60;
const MAX_POINTS = 4000;
const WIDTHS = [0.004, 0.008, 0.014, 0.022] as const;
/** Points closer than this (a fraction of the width) add nothing to a line but bytes. */
const MIN_STEP = 0.003;
const ERASE_RADIUS = 0.025;
/** One line holds this many points on the server; a longer stroke carries on as a new line. */
const STROKE_POINTS = 1000;
const labelSize = (w: number) => Math.max(12, w * 0.028);

const countPoints = (marks: Mark[]) => marks.reduce((n, m) => n + (m.type === "stroke" ? m.points.length : 1), 0);

type Tool = "pen" | "eraser" | "text";
const INK = "var(--vt-blocker)";

/** Saved drawings over an image, drawn in its own pixel space so line widths keep their proportion. */
export function MarksLayer({ marks, w, h, faint = false }: { marks: Mark[]; w: number; h: number; faint?: boolean }) {
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={`pointer-events-none absolute inset-0 h-full w-full ${faint ? "opacity-60" : ""}`} aria-hidden>
      {marks.map((m, i) => m.type === "stroke" && m.points.length === 1 ? (
        <circle key={i} cx={m.points[0][0] * w} cy={m.points[0][1] * h} r={(m.width * w) / 2} fill={INK} />
      ) : m.type === "stroke" ? (
        <polyline key={i} points={m.points.map(([x, y]) => `${x * w},${y * h}`).join(" ")} fill="none" stroke={INK}
          strokeWidth={m.width * w} strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <text key={i} x={m.x * w} y={m.y * h} fill={INK} fontSize={labelSize(w)} fontWeight={600}
          paintOrder="stroke" stroke="var(--vt-surface)" strokeWidth={Math.max(3, w * 0.006)} dominantBaseline="middle">
          {m.text}
        </text>
      ))}
    </svg>
  );
}

/**
 * Drawing on an attached image to say what to change: a marker in four thicknesses, an eraser that lifts a
 * whole line or label, and words placed where they apply. The drawing is saved with a written comment, so
 * the creator sees both in place on the same picture.
 */
export function ImageMarkup({ contentId, versionId, imageId, size, onDone, onCancel, children }: {
  contentId: number; versionId: number; imageId: string; size: { w: number; h: number };
  onDone: () => void; onCancel: () => void; children: React.ReactNode;
}) {
  const pad = useRef<SVGSVGElement>(null);
  const drawing = useRef<boolean>(false);
  // Set once a label is placed or cancelled, so the input's blur (as it unmounts) can't place it again.
  const settled = useRef(true);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [tool, setTool] = useState<Tool>("pen");
  const [width, setWidth] = useState<number>(WIDTHS[1]);
  const [placing, setPlacing] = useState<{ x: number; y: number } | null>(null);
  const [word, setWord] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const points = countPoints(marks);
  const full = marks.length >= MAX_MARKS || points >= MAX_POINTS;

  const spot = (e: React.PointerEvent): [number, number] => {
    const box = pad.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - box.left) / box.width)), Math.min(1, Math.max(0, (e.clientY - box.top) / box.height))];
  };
  const erase = (x: number, y: number) => {
    // Distances in fractions of the width, so the eraser is round on a tall or a wide picture alike.
    const ratio = size.h / size.w;
    const toSegment = ([ax, ay]: [number, number], [bx, by]: [number, number]) => {
      const dx = bx - ax, dy = (by - ay) * ratio, len = dx * dx + dy * dy;
      const t = len ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * ratio * dy) / len)) : 0;
      return Math.hypot(x - (ax + t * dx), (y - ay) * ratio - t * dy);
    };
    const hits = (m: Mark) => {
      if (m.type === "text") {
        // The label's own box: it starts at its anchor and runs right, about 0.6 of the type size a letter.
        const fs = labelSize(size.w) / size.w;
        return x >= m.x - ERASE_RADIUS && x <= m.x + m.text.length * fs * 0.6 + ERASE_RADIUS
          && Math.abs((y - m.y) * ratio) <= fs / 2 + ERASE_RADIUS;
      }
      const reach = ERASE_RADIUS + m.width / 2;
      return m.points.length === 1 ? toSegment(m.points[0], m.points[0]) < reach
        : m.points.some((pt, i) => i > 0 && toSegment(m.points[i - 1], pt) < reach);
    };
    setMarks((all) => all.filter((m) => !hits(m)));
  };

  const onDown = (e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    // Keeps focus where it is: otherwise the press that places a label blurs its new input, dropping it.
    e.preventDefault();
    const [x, y] = spot(e);
    if (tool === "text") {
      if (full) { setError(`A drawing holds up to ${MAX_MARKS} marks; erase some or save this one.`); return; }
      settled.current = false;
      setPlacing({ x, y });
      setWord("");
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    drawing.current = true;
    if (tool === "eraser") { erase(x, y); return; }
    if (full) { setError(`A drawing holds up to ${MAX_MARKS} marks; erase some or save this one.`); drawing.current = false; return; }
    setMarks((all) => [...all, { type: "stroke", points: [[x, y]], width }]);
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!drawing.current) return;
    const [x, y] = spot(e);
    if (tool === "eraser") { erase(x, y); return; }
    if (points >= MAX_POINTS || (marks.length >= MAX_MARKS && marks[marks.length - 1]?.type === "stroke"
        && (marks[marks.length - 1] as { points: unknown[] }).points.length >= STROKE_POINTS)) {
      drawing.current = false;
      setError("That is as much drawing as one comment holds; save it and start another.");
      return;
    }
    setMarks((all) => {
      const last = all[all.length - 1];
      // Counted from the marks being updated, not the last render, so a fast stroke can't overshoot.
      if (!last || last.type !== "stroke" || countPoints(all) >= MAX_POINTS) { drawing.current = false; return all; }
      const [px, py] = last.points[last.points.length - 1];
      if (Math.hypot(x - px, y - py) < MIN_STEP) return all;
      if (last.points.length >= STROKE_POINTS) {
        if (all.length >= MAX_MARKS) { drawing.current = false; return all; }
        return [...all, { type: "stroke", points: [[px, py], [x, y]], width: last.width }];
      }
      return [...all.slice(0, -1), { ...last, points: [...last.points, [x, y]] }];
    });
  };
  const onUp = () => { drawing.current = false; };

  const place = () => {
    if (settled.current) return;
    settled.current = true;
    const text = word.trim().slice(0, 120);
    if (placing && text) setMarks((all) => [...all, { type: "text", x: placing.x, y: placing.y, text }]);
    setPlacing(null);
    setWord("");
  };

  const save = async () => {
    if (saving) return;
    if (!note.trim()) { setError("Say what should change, so the drawing has words to go with it."); return; }
    setSaving(true);
    setError(null);
    try {
      // Fractions are rounded: four decimals is finer than any screen and keeps the request small.
      const r = (v: number) => Math.round(v * 10000) / 10000;
      const clean: Mark[] = marks.map((m) => m.type === "stroke"
        ? { ...m, points: m.points.map(([x, y]) => [r(x), r(y)] as [number, number]) }
        : { ...m, x: r(m.x), y: r(m.y) });
      await addPinnedComment(contentId, { body: note.trim(), version_id: versionId, media_id: imageId, marks: clean.length ? clean : undefined });
      onDone();
    } catch (err) {
      setError(shownError(err, "The comment wasn't saved."));
    } finally {
      setSaving(false);
    }
  };

  const toolButton = (t: Tool, label: string) => (
    <button type="button" onClick={() => { setTool(t); setPlacing(null); }} aria-pressed={tool === t}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${tool === t ? "bg-ink text-surface" : "text-muted hover:bg-sunken hover:text-ink"}`}>
      {label}
    </button>
  );

  return (
    <div className="flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-lg border-2 border-accent/60 bg-sunken">
      {children}
      <svg ref={pad} viewBox={`0 0 ${size.w} ${size.h}`} role="img" aria-label="Drawing area over the image"
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        className={`absolute inset-0 z-10 h-full w-full touch-none ${tool === "text" ? "cursor-text" : tool === "eraser" ? "cursor-cell" : "cursor-crosshair"}`}>
        <rect width={size.w} height={size.h} fill="transparent" />
      </svg>
      <div className="pointer-events-none absolute inset-0 z-10"><MarksLayer marks={marks} w={size.w} h={size.h} /></div>
      {placing && (
        <div className="absolute z-20 -translate-y-1/2" style={{ left: `${Math.min(placing.x, 0.55) * 100}%`, top: `${placing.y * 100}%` }}>
          <input autoFocus value={word} maxLength={120} onChange={(e) => setWord(e.target.value)} aria-label="Text to place"
            onKeyDown={(e) => { if (e.key === "Enter") place(); if (e.key === "Escape") { settled.current = true; setPlacing(null); } }} onBlur={place}
            placeholder="Type, then Enter" className="vt-input h-8 w-48 py-0 text-xs shadow-lg" />
        </div>
      )}
      </div>
      {/* The toolbar and the comment sit under the picture, outside the drawing area. */}
      <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-3">
        <div className="flex flex-wrap items-center gap-1">
          <div role="group" aria-label="Tool" className="flex gap-0.5 rounded-lg bg-sunken/60 p-0.5">
            {toolButton("pen", "Marker")}
            {toolButton("eraser", "Eraser")}
            {toolButton("text", "Text")}
          </div>
          <div role="group" aria-label="Thickness" className="ml-2 flex items-center gap-1">
            {WIDTHS.map((w) => (
              <button key={w} type="button" onClick={() => { setWidth(w); setTool("pen"); }} aria-pressed={width === w}
                aria-label={`Thickness ${WIDTHS.indexOf(w) + 1} of ${WIDTHS.length}`}
                className={`flex h-7 w-7 items-center justify-center rounded-md transition ${width === w ? "bg-sunken ring-1 ring-line-strong" : "hover:bg-sunken"}`}>
                <span className="rounded-full bg-[var(--vt-blocker)]" style={{ width: 3 + WIDTHS.indexOf(w) * 3, height: 3 + WIDTHS.indexOf(w) * 3 }} />
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setMarks((m) => m.slice(0, -1))} disabled={!marks.length}
            className="ml-auto rounded-md px-2 py-1 text-xs text-muted hover:bg-sunken hover:text-ink disabled:opacity-40">Undo</button>
          <button type="button" onClick={() => setMarks([])} disabled={!marks.length}
            className="rounded-md px-2 py-1 text-xs text-muted hover:bg-sunken hover:text-ink disabled:opacity-40">Clear</button>
        </div>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={5000} rows={2}
          aria-label="Comment for this drawing" placeholder="What should change in the picture?"
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) save(); }}
          className="vt-input resize-y text-sm" />
        {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
        <div className="flex items-center gap-2">
          <button type="button" onClick={save} disabled={saving} className="vt-btn vt-btn-primary h-8 text-xs">
            {saving ? "Saving…" : "Post comment"}
          </button>
          <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet h-8 text-xs">Cancel</button>
          <span className="ml-auto text-xs tabular-nums text-subtle">{marks.length} mark{marks.length === 1 ? "" : "s"}</span>
        </div>
      </div>
    </div>
  );
}

/** Comments pinned to one image, newest last, for the list under it. */
export const pinnedTo = (comments: PinnedComment[], imageId: string) =>
  comments.filter((c) => c.media_id === imageId && c.time_start == null);

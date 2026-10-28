"use client";

import { useState } from "react";
import { relativeTime, versionImageUrl } from "@/lib/review-client";
import type { ContentDetail, Finding, Level, PinnedComment } from "@/lib/types";
import { ImageMarkup, MarksLayer, pinnedTo } from "./ImageMarkup";
import { ReviewVideo } from "./ReviewVideo";

type Version = ContentDetail["versions"][number];
const RING: Record<Level, string> = {
  blocker: "border-[var(--vt-blocker)]",
  warning: "border-[var(--vt-warning)]",
  advisory: "border-[var(--vt-advisory)]",
};

/**
 * The images and videos that were checked, as the reviewer would see them in the feed. On an image each
 * finding's region is outlined; on a video each finding sits on the timeline at its moment. Either is a
 * button: picking it opens that finding in the list, and picking a finding in the list shows it here.
 * Comments pinned to a picture or a stretch of video show in place, for both sides of the review.
 */
export function Attachments({ contentId, version, findings, active, onSelect, comments = [], onPinned, canComment = false }: {
  contentId: number;
  version: Version;
  findings: Finding[];
  active: number | null;
  onSelect: (id: number) => void;
  comments?: PinnedComment[];
  onPinned?: () => void;
  canComment?: boolean;
}) {
  const images = version.images ?? [];
  const videos = version.videos ?? [];
  if (images.length === 0 && videos.length === 0) return null;
  const mine = comments.filter((c) => c.version_id === version.id);
  return (
    <div className="mt-6 flex flex-col gap-6 border-t border-line pt-5">
      {videos.length > 0 && (
        <section aria-label="Attached videos">
          <p className="mb-3 text-xs font-medium text-muted">Attached {videos.length === 1 ? "video" : `videos (${videos.length})`}</p>
          <ul className="flex flex-col gap-6">
            {videos.map((v) => (
              <li key={v.id}>
                <ReviewVideo contentId={contentId} versionId={version.id} video={v} findings={findings} comments={mine}
                  active={active} onSelect={onSelect} onPinned={() => onPinned?.()} canComment={canComment} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {images.length > 0 && (
        <section aria-label="Attached images">
          <p className="mb-3 text-xs font-medium text-muted">Attached {images.length === 1 ? "image" : `images (${images.length})`}</p>
          <ul className={`grid gap-4 ${images.length > 1 ? "sm:grid-cols-2" : ""}`}>
            {images.map((img) => (
              <Figure key={img.id} contentId={contentId} versionId={version.id} imageId={img.id}
                src={versionImageUrl(contentId, version.id, img.id)} alt={img.alt} decorative={img.decorative}
                name={img.id} marks={marksOn(findings, img.id)} active={active} onSelect={onSelect}
                notes={pinnedTo(mine, img.id)} onPinned={() => onPinned?.()} canComment={canComment} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Findings to outline on one image: its own, and those elsewhere that cite text read off it. */
function marksOn(findings: Finding[], id: string): Finding[] {
  return findings.flatMap((f) => {
    const own = f.locator?.image === `img:${id}` ? [f] : [];
    const cited = (f.locator?.evidence ?? [])
      .filter((e) => e.source.startsWith(`img:${id}:`) && e.box?.length === 4)
      .map((e) => ({ ...f, locator: { ...f.locator, image: `img:${id}`, box: e.box } }));
    return [...own, ...cited];
  });
}

function Figure({ contentId, versionId, imageId, src, alt, decorative, name, marks, active, onSelect, notes, onPinned, canComment }: {
  contentId: number; versionId: number; imageId: string;
  src: string; alt: string | null; decorative: boolean; name: string; marks: Finding[];
  active: number | null; onSelect: (id: number) => void;
  notes: PinnedComment[]; onPinned: () => void; canComment: boolean;
}) {
  // Boxes are in the image's own pixels; they are placed as fractions of its natural size once it loads.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [showNotes, setShowNotes] = useState(true);
  const boxed = marks.filter((f) => Array.isArray(f.locator?.box) && f.locator!.box!.length === 4);
  const drawn = notes.flatMap((c) => c.marks ?? []);
  const picture = failed ? (
    <p className="px-4 py-10 text-center text-xs text-muted">This image couldn&apos;t be loaded.</p>
  ) : (
    // eslint-disable-next-line @next/next/no-img-element -- served by the API behind the session, not a static asset
    <img src={src} alt={alt ?? ""} className="block h-auto w-full select-none" loading="lazy" draggable={false}
      onContextMenu={(e) => e.preventDefault()}
      onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
      onError={() => setFailed(true)} />
  );
  if (drawing && size) {
    return (
      <li className="sm:col-span-2">
        <ImageMarkup contentId={contentId} versionId={versionId} imageId={imageId} size={size}
          onDone={() => { setDrawing(false); onPinned(); }} onCancel={() => setDrawing(false)}>
          {picture}
        </ImageMarkup>
      </li>
    );
  }
  return (
    <li>
      <figure className="flex flex-col gap-2">
        <div className="relative overflow-hidden rounded-lg border border-line bg-sunken">
          {picture}
          {size && showNotes && drawn.length > 0 && <MarksLayer marks={drawn} w={size.w} h={size.h} />}
          {size && boxed.map((f, i) => {
            const [x0, y0, x1, y1] = f.locator!.box!;
            const on = active === f.id;
            return (
              <button key={`${f.id}-${i}`} type="button" onClick={() => onSelect(f.id)} aria-label={`${f.title}: show this issue`}
                title={f.title} aria-pressed={on}
                className={`absolute rounded-md border-2 transition-[box-shadow,background-color] duration-200 ${RING[f.level]} ${
                  on ? "bg-accent/10 shadow-[0_0_0_4px_color-mix(in_srgb,var(--vt-accent)_35%,transparent)]" : "border-dashed hover:bg-accent/5"}`}
                style={{ left: `${(x0 / size.w) * 100}%`, top: `${(y0 / size.h) * 100}%`,
                  width: `${((x1 - x0) / size.w) * 100}%`, height: `${((y1 - y0) / size.h) * 100}%` }} />
            );
          })}
        </div>
        <figcaption className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
          <span className="font-medium text-ink">{name}</span>
          <span>{decorative ? "Decorative" : alt ? `Alt text: “${alt}”` : <span className="text-[var(--vt-warning)]">No alt text</span>}</span>
          {marks.length > 0 && <span className="text-subtle">· {marks.length} issue{marks.length === 1 ? "" : "s"}</span>}
          <span className="ml-auto flex gap-1">
            {drawn.length > 0 && (
              <button type="button" onClick={() => setShowNotes(!showNotes)} aria-pressed={showNotes}
                className="rounded-md px-2 py-0.5 text-xs text-muted transition hover:bg-sunken hover:text-ink">
                {showNotes ? "Hide drawings" : "Show drawings"}
              </button>
            )}
            {canComment && size && !failed && (
              <button type="button" onClick={() => setDrawing(true)}
                className="rounded-md px-2 py-0.5 text-xs font-medium text-accent transition hover:bg-accent/10">Mark up</button>
            )}
          </span>
        </figcaption>
        {notes.length > 0 && (
          <ul className="flex flex-col gap-1.5" aria-label="Comments on this image">
            {notes.map((c) => (
              <li key={c.id} className="rounded-lg border border-line bg-sunken/50 px-3 py-2 text-xs">
                <span className="text-subtle">{relativeTime(c.created_at)}{c.marks?.length ? ` · ${c.marks.length} mark${c.marks.length === 1 ? "" : "s"}` : ""}</span>
                <p className="mt-0.5 whitespace-pre-wrap text-ink">{c.body}</p>
              </li>
            ))}
          </ul>
        )}
      </figure>
    </li>
  );
}

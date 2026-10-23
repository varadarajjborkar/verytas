"use client";

import { useState } from "react";
import { versionImageUrl } from "@/lib/review-client";
import type { ContentDetail, Finding, Level } from "@/lib/types";

type Version = ContentDetail["versions"][number];
const RING: Record<Level, string> = {
  blocker: "border-[var(--vt-blocker)]",
  warning: "border-[var(--vt-warning)]",
  advisory: "border-[var(--vt-advisory)]",
};

/**
 * The images that were checked, as the reviewer would see them in the feed, with each finding's region
 * outlined. A region is a button: picking it opens that finding in the list, and picking a finding in
 * the list highlights its region here, the same way highlights in the text work.
 */
export function Attachments({ contentId, version, findings, active, onSelect }: {
  contentId: number;
  version: Version;
  findings: Finding[];
  active: number | null;
  onSelect: (id: number) => void;
}) {
  const images = version.images ?? [];
  if (images.length === 0) return null;
  return (
    <div className="mt-6 border-t border-line pt-5">
      <p className="mb-3 text-xs font-medium text-muted">Attached {images.length === 1 ? "image" : `images (${images.length})`}</p>
      <ul className={`grid gap-4 ${images.length > 1 ? "sm:grid-cols-2" : ""}`}>
        {images.map((img) => (
          <Figure key={img.id} src={versionImageUrl(contentId, version.id, img.id)} alt={img.alt} decorative={img.decorative}
            name={img.id} marks={marksOn(findings, img.id)} active={active} onSelect={onSelect} />
        ))}
      </ul>
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

function Figure({ src, alt, decorative, name, marks, active, onSelect }: {
  src: string; alt: string | null; decorative: boolean; name: string; marks: Finding[];
  active: number | null; onSelect: (id: number) => void;
}) {
  // Boxes are in the image's own pixels; they are placed as fractions of its natural size once it loads.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const boxed = marks.filter((f) => Array.isArray(f.locator?.box) && f.locator!.box!.length === 4);
  return (
    <li>
      <figure className="flex flex-col gap-2">
        <div className="relative overflow-hidden rounded-lg border border-line bg-sunken">
          {failed ? (
            <p className="px-4 py-10 text-center text-xs text-muted">This image couldn&apos;t be loaded.</p>
          ) : (
            // eslint-disable-next-line @next/next/no-img-element -- served by the API behind the session, not a static asset
            <img src={src} alt={alt ?? ""} className="block h-auto w-full" loading="lazy"
              onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
              onError={() => setFailed(true)} />
          )}
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
        </figcaption>
      </figure>
    </li>
  );
}

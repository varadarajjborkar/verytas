"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { ContentDetail, Finding, SourceInfo } from "@/lib/types";
import { ChevronIcon } from "../Icons";
import { DocumentPreviewPane, SheetTable } from "./DocumentPreview";
import { HighlightedBody } from "./parts";

type Version = ContentDetail["versions"][number];
// pinned: about particular words, marked where they are; whole: about the page as a whole (tone, a missing
// disclosure), listed above its text, because a mark over everything would hide the precise ones under it.
type Part = { source: SourceInfo; label: string; pinned: Finding[]; whole: Finding[] };
type Page = { key: string; number: number; label: string; parts: Part[]; issues: number };

const KIND_WORD: Record<string, string> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
  "text/html": "HTML",
};

/**
 * The attached documents as they were read, page by page (a slide, a sheet and a web page are pages), with
 * every finding marked in place the way the post's own text is: picking a mark opens that issue in the list,
 * and picking an issue in the list brings its mark into view. Pages with issues start open; clean pages fold
 * away, so a long PDF does not bury the one page that matters. Text read off a picture in the document is
 * shown under its page.
 */
// Kinds that can be seen as they look: page pictures (PDF; Word and PowerPoint through LibreOffice) or the page.
const PREVIEWABLE = new Set(["PDF", "Word", "PowerPoint", "HTML"]);

export function DocumentPages({ contentId, version, sources, findings, active, onSelect, kept }: {
  contentId: number;
  version: Version;
  sources: SourceInfo[];
  findings: Finding[];
  active: number | null;
  onSelect: (id: number) => void;
  /** Findings already decided (kept as they are, or ticked off): still marked, quietly, as in the post. */
  kept?: Set<number>;
}) {
  const docs = useMemo(() => group(version, sources, findings), [version, sources, findings]);
  // Each document's issues as one stable list, so its preview is not rebuilt on every render.
  const issuesOf = useMemo(() => new Map(docs.map((d) => [d.id,
    d.pages.flatMap((p) => p.parts.flatMap((x) => [...x.pinned, ...x.whole]))])), [docs]);
  const box = useRef<HTMLDivElement>(null);
  // Pages flipped from their default: open when they have issues, folded when they have none.
  const [flipped, setFlipped] = useState<Set<string>>(new Set());
  const [showClean, setShowClean] = useState<Set<string>>(new Set());
  const [previewing, setPreviewing] = useState<Set<string>>(new Set());
  // The page holding the picked issue opens for it; closing it then is remembered for that issue only.
  const [closedFor, setClosedFor] = useState<Set<string>>(new Set());

  // An issue picked in the list opens its page and scrolls its words into view.
  const activeKey = useMemo(() => {
    for (const d of docs) for (const p of d.pages) if (p.parts.some((x) => [...x.pinned, ...x.whole].some((f) => f.id === active))) return p.key;
    return null;
  }, [docs, active]);
  useEffect(() => {
    if (active == null || activeKey == null) return;
    requestAnimationFrame(() => box.current?.querySelector(`[data-id="${active}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }, [active, activeKey]);

  if (docs.length === 0) return null;
  const toggle = (set: typeof setFlipped, key: string) => set((s) => {
    const next = new Set(s);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  return (
    <div ref={box} className="mt-6 flex flex-col gap-5 border-t border-line pt-5">
      {docs.map((d) => {
        const flagged = d.pages.filter((p) => p.issues > 0);
        const clean = d.pages.filter((p) => p.issues === 0);
        const shown = showClean.has(d.id) ? d.pages : flagged;
        return (
          <section key={d.id} aria-label={`Document ${d.name}`}>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="flex flex-wrap items-baseline gap-x-2 text-xs font-normal text-muted">
                <span className="font-medium text-ink">{d.name}</span>
                {d.kind && <span>{d.kind}</span>}
                <span className="text-subtle">· {d.pages.length} {d.unit}{d.pages.length === 1 ? "" : "s"} read
                  {flagged.length > 0 ? `, ${d.issues} issue${d.issues === 1 ? "" : "s"} on ${flagged.length}` : ", no issues"}</span>
              </h3>
              {PREVIEWABLE.has(d.kind) && (
                <div role="group" aria-label={`How to show ${d.name}`} className="flex rounded-lg border border-line p-0.5 text-xs">
                  {(["Text", "Preview"] as const).map((mode) => {
                    const on = (mode === "Preview") === previewing.has(d.id);
                    return (
                      <button key={mode} type="button" aria-pressed={on} onClick={() => { if (!on) toggle(setPreviewing, d.id); }}
                        className={`rounded-md px-2.5 py-1 ${on ? "bg-sunken font-medium text-ink" : "text-muted hover:text-ink"}`}>
                        {mode}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            {previewing.has(d.id) ? (
              <DocumentPreviewPane contentId={contentId} versionId={version.id} docId={d.id} active={active} onSelect={onSelect}
                findings={issuesOf.get(d.id) ?? []} />
            ) : (<>
            <ul className="flex flex-col gap-2">
              {shown.map((p) => {
                const forActive = p.key === activeKey ? `${p.key}@${active}` : null;
                const isOpen = forActive ? !closedFor.has(forActive) : (p.issues > 0) !== flipped.has(p.key);
                const flip = () => (forActive ? toggle(setClosedFor, forActive) : toggle(setFlipped, p.key));
                const body = `doc-page-${p.key.replace(/[^\w-]/g, "-")}`;
                return (
                  <li key={p.key} className="rounded-xl border border-line bg-sunken/40">
                    <button type="button" onClick={flip} aria-expanded={isOpen} aria-controls={body}
                      className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-sm">
                      <span className="font-medium first-letter:uppercase">{p.label}</span>
                      <span className="flex items-center gap-2 text-xs text-muted">
                        {p.issues > 0 ? `${p.issues} issue${p.issues === 1 ? "" : "s"}` : "No issues"}
                        <ChevronIcon size={14} className={`transition-transform ${isOpen ? "rotate-180" : ""}`} />
                      </span>
                    </button>
                    {isOpen && (
                      <div id={body} className="flex flex-col gap-3 border-t border-line px-3.5 py-3">
                        {p.parts.map((x) => {
                          const mine = [...x.pinned, ...x.whole].some((f) => f.id === active);
                          return <PagePart key={x.source.id} part={x} unit={d.unit} active={mine ? active : null}
                            onSelect={onSelect} kept={kept} />;
                        })}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
            {clean.length > 0 && !previewing.has(d.id) && (
              <button type="button" onClick={() => toggle(setShowClean, d.id)} aria-expanded={showClean.has(d.id)}
                className="mt-2 text-xs text-muted underline-offset-2 hover:text-ink hover:underline">
                {showClean.has(d.id) ? `Hide the ${clean.length} without issues`
                  : `Show the ${clean.length} ${d.unit}${clean.length === 1 ? "" : "s"} without issues`}
              </button>
            )}
            </>)}
          </section>
        );
      })}
    </div>
  );
}

/** One text of a page (its own, or what was read off a picture on it). Memoised: picking an issue re-renders
 * only the part that holds it, not every open page of a long document. */
const PagePart = memo(function PagePart({ part: x, unit, active, onSelect, kept }: {
  part: Part; unit: string; active: number | null; onSelect: (id: number) => void; kept?: Set<number>;
}) {
  const cut = x.source.chars > [...x.source.text].length;
  return (
    <div className="min-w-0">
      {x.label && <p className="mb-1 text-xs font-medium text-muted">{x.label}</p>}
      {x.whole.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-subtle">About the whole {unit}:</span>
          {x.whole.map((f) => (
            <button key={f.id} type="button" data-id={f.id} onClick={() => onSelect(f.id)}
              aria-pressed={active === f.id} title={f.title}
              className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-colors ${
                active === f.id ? "border-accent bg-accent/10 text-ink" : "border-line text-muted hover:text-ink"} ${
                kept?.has(f.id) ? "opacity-60" : ""}`}>
              <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: `var(--vt-${f.level})` }} />
              <span className="truncate">{f.title}</span>
            </button>
          ))}
        </div>
      )}
      {x.source.kind === "xlsx_text" ? (
        <SheetTable text={x.source.text} findings={x.pinned} active={active} onSelect={onSelect} />
      ) : (
        <div className="max-h-96 overflow-auto rounded-lg">
          <HighlightedBody body={x.source.text} findings={x.pinned} active={active} onSelect={onSelect}
            innerRef={{ current: null }} kept={kept} />
        </div>
      )}
      {cut && (
        <p className="mt-1.5 text-xs text-subtle">
          Shown up to {[...x.source.text].length.toLocaleString()} of {x.source.chars.toLocaleString()} characters;
          issues further on are listed above. Use Preview to see the whole {unit}.
        </p>
      )}
    </div>
  );
}, (a, b) => a.part === b.part && a.unit === b.unit && a.active === b.active && a.onSelect === b.onSelect
  // Decisions on other pages' issues change the kept set; only this part's own issues matter here.
  && [...a.part.pinned, ...a.part.whole].every((f) => !!a.kept?.has(f.id) === !!b.kept?.has(f.id)));

/** Sources come as doc:<id>:p<n>:text (a page's own text) and doc:<id>:p<n>:img<k>:ocr and the like (text
 * read off a picture on that page); grouped by document, then page. */
function group(version: Version, sources: SourceInfo[], findings: Finding[]) {
  const named = new Map((version.documents ?? []).map((d) => [d.id, d]));
  const docs = new Map<string, { id: string; name: string; kind: string; unit: string; issues: number;
    pages: Map<number, Page> }>();
  for (const s of sources) {
    const m = /^doc:(.+?):p(\d+):(.+)$/.exec(s.id);
    if (!m) continue;
    const [, docId, num, rest] = m;
    const number = Number(num);
    const meta = named.get(docId);
    const doc = docs.get(docId) ?? { id: docId, name: meta?.name || docId, kind: meta ? KIND_WORD[meta.media_type] ?? "" : "",
      unit: unitOf(meta?.media_type, s), issues: 0, pages: new Map<number, Page>() };
    docs.set(docId, doc);
    const label = typeof s.locator?.label === "string" ? s.locator.label : `page ${number}`;
    const page = doc.pages.get(number) ?? { key: `${docId}:${number}`, number, label, parts: [], issues: 0 };
    doc.pages.set(number, page);
    const length = [...s.text].length;  // findings count in code points, and the stored text may be cut
    const own = findings.filter((f) => f.source === s.id);
    // A span within the stored text that leaves most of it out is about particular words; one that covers
    // most of a short sheet or slide is about the whole of it.
    const pinpoint = (f: Finding) => f.span_start != null && f.span_end != null && f.span_end <= length
      && f.span_end > f.span_start && (f.span_end - f.span_start <= 30 || f.span_end - f.span_start < length * 0.6);
    page.parts.push({ source: s, label: partLabel(rest), pinned: own.filter(pinpoint), whole: own.filter((f) => !pinpoint(f)) });
    page.issues += own.length;
    doc.issues += own.length;
  }
  return [...docs.values()].map((d) => ({
    ...d,
    pages: [...d.pages.values()].sort((a, b) => a.number - b.number).map((p) => ({
      ...p, parts: p.parts.sort((a, b) => (a.label ? 1 : 0) - (b.label ? 1 : 0)),
    })),
  }));
}

function unitOf(type: string | undefined, s: SourceInfo): string {
  if (type?.includes("presentationml") || s.kind === "pptx_text") return "slide";
  if (type?.includes("spreadsheetml") || s.kind === "xlsx_text") return "sheet";
  return "page";
}

function partLabel(rest: string): string {
  if (rest === "text") return "";
  if (rest === "scan:ocr" || rest.startsWith("scan")) return "Read from the scanned page";
  if (rest.startsWith("drawn")) return "Text drawn as shapes";
  const pic = /^img(\d+)/.exec(rest);
  return pic ? `Text in picture ${pic[1]}` : "";
}

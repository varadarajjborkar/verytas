"use client";

import { useEffect, useMemo, useState } from "react";
import { documentPageUrl, getDocumentPreview, type DocumentPreview } from "@/lib/review-client";
import type { Finding, Level } from "@/lib/types";
import { HighlightedBody } from "./parts";

const RING: Record<Level, string> = {
  blocker: "border-[var(--vt-blocker)]",
  warning: "border-[var(--vt-warning)]",
  advisory: "border-[var(--vt-advisory)]",
};

/** A document as it looks: page pictures from the API (a PDF, or Word and PowerPoint turned into one) with a
 * box on each finding's words, or a web page in a locked frame. Fetched only when asked for. */
export function DocumentPreviewPane({ contentId, versionId, docId, findings, active, onSelect }: {
  contentId: number; versionId: number; docId: string; findings: Finding[];
  active: number | null; onSelect: (id: number) => void;
}) {
  const [state, setState] = useState<{ data?: DocumentPreview; error?: string }>({});
  useEffect(() => {
    let live = true;
    getDocumentPreview(contentId, versionId, docId)
      .then((data) => { if (live) setState({ data }); })
      .catch((e: Error) => { if (live) setState({ error: e.message }); });
    return () => { live = false; };
  }, [contentId, versionId, docId]);

  if (state.error) return <p role="alert" className="py-6 text-center text-xs text-muted">Couldn&apos;t make the preview: {state.error}</p>;
  if (!state.data) return <p role="status" className="py-6 text-center text-xs text-muted">Making the preview… a deck or Word file takes a few seconds the first time.</p>;
  if (state.data.kind === "html") return <WebPage html={state.data.html} findings={findings} />;
  const byId = new Map(findings.map((f) => [f.id, f]));
  const { pages, marks, total_pages: total } = state.data;
  return (
    <>
    {total > pages.length && (
      <p className="mb-2 text-xs text-subtle">Showing the first {pages.length} of {total} pages; the text view has every page.</p>
    )}
    <ol className="flex flex-col gap-4">
      {pages.map((size, i) => {
        const here = marks.filter((m) => m.page === i + 1 && byId.has(m.finding_id));
        return (
          <li key={i} className="flex flex-col gap-1.5">
            <div className="vt-page relative overflow-hidden rounded-lg border border-line bg-white" style={{ aspectRatio: `${size.width} / ${size.height}` }}>
              {/* eslint-disable-next-line @next/next/no-img-element -- rendered by the API behind the session */}
              <img src={documentPageUrl(contentId, versionId, docId, i + 1)} alt={`Page ${i + 1}`} loading="lazy"
                className="absolute inset-0 h-full w-full" />
              {here.map((m, k) => {
                const f = byId.get(m.finding_id)!;
                const [x0, y0, x1, y1] = m.box;
                const on = active === f.id;
                return (
                  <button key={`${f.id}-${k}`} type="button" data-id={f.id} onClick={() => onSelect(f.id)} title={f.title}
                    aria-label={`${f.title}: show this issue`} aria-pressed={on}
                    className={`absolute rounded border-2 transition-[box-shadow,background-color] duration-200 ${RING[f.level]} ${
                      on ? "bg-accent/15 shadow-[0_0_0_4px_color-mix(in_srgb,var(--vt-accent)_35%,transparent)]" : "hover:bg-accent/10"}`}
                    style={{ left: `${(x0 / size.width) * 100}%`, top: `${(y0 / size.height) * 100}%`,
                      width: `${((x1 - x0) / size.width) * 100}%`, height: `${((y1 - y0) / size.height) * 100}%` }} />
                );
              })}
            </div>
            <p className="text-xs text-subtle">Page {i + 1}{here.length > 0 ? ` · ${new Set(here.map((m) => m.finding_id)).size} marked` : ""}</p>
          </li>
        );
      })}
    </ol>
    </>
  );
}

/** A web page shown as it looks, safely: no scripts (an empty sandbox), nothing fetched (a content policy that
 * allows only inline pictures and styles), and the flagged words marked in the page's own text. */
function WebPage({ html, findings }: { html: string; findings: Finding[] }) {
  const srcDoc = useMemo(() => lockedPage(html, findings), [html, findings]);
  return (
    <div className="flex flex-col gap-1.5">
      <iframe title="The web page as it looks" sandbox="" referrerPolicy="no-referrer" srcDoc={srcDoc}
        className="vt-page h-[36rem] w-full resize-y rounded-lg border border-line bg-white" />
      <p className="text-xs text-subtle">Shown with its scripts off and nothing loaded from the internet. Marks show where
        each issue is; pick an issue from the list to work on it.</p>
    </div>
  );
}

const MARK_COLOUR: Record<Level, string> = { blocker: "#f6c9c0", warning: "#f6e0b5", advisory: "#d6e4f7" };

function lockedPage(html: string, findings: Finding[]): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  // SVG animation can rewrite an attribute after this cleanup ran (an <animate> setting a link's href).
  doc.querySelectorAll("script, iframe, frame, frameset, object, embed, applet, base, link, meta, template, audio, video, "
    + "source, track, portal, noscript, animate, set, animateMotion, animateTransform, discard, foreignObject")
    .forEach((el) => el.remove());
  if (!doc.body) doc.documentElement.append(doc.createElement("body"));  // a frameset page has none
  // Nothing outside the file may load, not even a picture: a tracking pixel would tell its owner who
  // reviewed the page, and when. Every attribute that can carry an address is checked, whatever its name or
  // namespace (SVG's xlink:href); anything not an inline picture is cut. The content policy below is the
  // second lock, not the only one.
  const inlinePicture = (v: string) => /^\s*data:image\/(png|jpe?g|gif|webp);/i.test(v);
  for (const el of Array.from(doc.querySelectorAll("*"))) {
    for (const attr of Array.from(el.attributes)) {
      const name = attr.name.toLowerCase();
      if (name.startsWith("on") || name === "srcdoc" || name === "srcset" || name === "ping") {
        el.removeAttribute(attr.name);
      } else if (/(^|:)(src|href|poster|background|action|formaction|data|codebase|cite|longdesc|lowsrc|dynsrc)$/.test(name)) {
        if (name.endsWith("href") && el.localName === "a") el.setAttribute(attr.name, "#");
        else if (!inlinePicture(attr.value)) el.removeAttribute(attr.name);
      }
    }
  }
  // CSS that could fetch is dropped whole rather than rewritten: escapes ("u\\72l("), image-set() and
  // @import make a rewrite a guessing game. Plain styling stays.
  const risky = (css: string) => /\\|url\s*\(|image-set|@import|expression\s*\(|binding/i.test(css);
  doc.querySelectorAll("[style]").forEach((el) => { if (risky(el.getAttribute("style") ?? "")) el.removeAttribute("style"); });
  doc.querySelectorAll("style").forEach((el) => { if (risky(el.textContent ?? "")) el.remove(); });
  const csp = doc.createElement("meta");
  csp.httpEquiv = "Content-Security-Policy";
  csp.content = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:";
  doc.head.prepend(csp);
  // Quotes match across any run of spacing (a page wraps lines where the source did not).
  const quotes = findings.map((f) => ({ q: (f.quote ?? "").trim(), level: f.level, title: f.title }))
    .filter((x) => x.q.length >= 2 && x.q.length <= 300)
    .map((x) => ({ ...x, re: new RegExp(x.q.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"), "i") }));
  if (quotes.length > 0) {
    // Only text people read: not inside a title, a form field's value or what is left of a style block.
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => n.parentElement?.closest("style, textarea, title, select, option, script")
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const nodes: Text[] = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) nodes.push(n as Text);
    // Every issue in a text node is marked, earliest first; a quote that runs across two elements (a bold
    // word inside it) is not found here and is still listed with its page.
    for (const start of nodes) {
      let node: Text | null = start;
      while (node) {
        let best: { m: RegExpExecArray; level: Level; title: string } | null = null;
        for (const { re, level, title } of quotes) {
          const m = re.exec(node.data ?? "");
          if (m && m[0].length > 0 && (!best || m.index < best.m.index)) best = { m, level, title };
        }
        if (!best) break;
        const hit = node.splitText(best.m.index);
        const rest = hit.splitText(best.m[0].length);
        const mark = doc.createElement("mark");
        mark.title = best.title;
        mark.setAttribute("style", `background:${MARK_COLOUR[best.level]};color:inherit;border-radius:3px;padding:0 2px`);
        hit.replaceWith(mark);
        mark.append(hit);
        node = rest.data ? rest : null;
      }
    }
  }
  return `<!DOCTYPE html>${doc.documentElement.outerHTML}`;
}

/** A sheet read as its table, cells with issues tinted and their words marked. The review reads a sheet as
 * "[name]", a header row and rows, cells joined by " | "; findings point into that text. */
export function SheetTable({ text, findings, active, onSelect }: {
  text: string; findings: Finding[]; active: number | null; onSelect: (id: number) => void;
}) {
  const rows = useMemo(() => cells(text), [text]);
  return (
    <div className="max-h-[28rem] overflow-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-sm">
        <tbody>
          {rows.map((row, r) => (
            <tr key={r} className={r === 0 ? "sticky top-0 bg-raised text-xs font-medium text-muted" : "border-t border-line"}>
              {row.map((c, k) => {
                const mine = findings.filter((f) => f.span_start != null && f.span_end != null
                  && f.span_start < c.end && f.span_end > c.start)
                  .map((f) => ({ ...f, span_start: Math.max(0, f.span_start! - c.start), span_end: Math.min(c.end, f.span_end!) - c.start }));
                const Tag = r === 0 ? "th" : "td";
                return (
                  <Tag key={k} className={`border-l border-line px-2.5 py-1.5 text-left align-top first:border-l-0 ${
                    mine.length ? "bg-[color-mix(in_srgb,var(--vt-warning)_10%,transparent)]" : ""}`}>
                    {mine.length ? <HighlightedBody body={c.text} findings={mine} active={active} onSelect={onSelect}
                      innerRef={{ current: null }} /> : c.text}
                  </Tag>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Cells with their code-point offsets in the sheet's text (findings count code points). */
function cells(text: string): { text: string; start: number; end: number }[][] {
  const out: { text: string; start: number; end: number }[][] = [];
  let pos = 0;
  for (const line of text.split("\n")) {
    const len = [...line].length;
    if (!(out.length === 0 && /^\[.*\]$/.test(line))) {  // the "[Sheet]" title line is the page label already
      const row: { text: string; start: number; end: number }[] = [];
      let at = pos;
      for (const part of line.split(" | ")) {
        const n = [...part].length;
        row.push({ text: part, start: at, end: at + n });
        at += n + 3;
      }
      out.push(row);
    }
    pos += len + 1;
  }
  return out;
}

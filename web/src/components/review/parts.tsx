"use client";

// Pieces of the review screen shared by the review view and the page shell.

import { useState } from "react";
import { aiEdit } from "@/lib/review-client";
import type { CategoryScore, Finding, Level } from "@/lib/types";
import { useToast } from "../Toaster";
import { Details } from "../ui";

export const LEVEL_ORDER: Level[] = ["blocker", "warning", "advisory"];
// How each coverage status reads on the scorecard. Anything other than "checked" is never shown as a pass.
export const COVERAGE_LABEL: Record<string, { text: string; tone: string }> = {
  not_checked: { text: "Not checked", tone: "text-[var(--vt-blocker)]" },
  not_configured: { text: "No rules yet", tone: "text-muted" },
  degraded: { text: "Heuristic only", tone: "text-[var(--vt-warning)]" },
};

export function AiEditBox({ contentId, onUse }: { contentId: number; onUse: (body: string) => void }) {
  const toast = useToast();
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [proposal, setProposal] = useState<{ body: string; changes: string[]; remaining: string[]; model: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask() {
    setBusy(true);
    setError(null);
    try {
      setProposal(await aiEdit(contentId, instruction));
      toast({ kind: "success", title: "Rewrite ready" });
    } catch (err) {
      setError((err as Error).message);
      toast({ kind: "error", title: "Couldn't rewrite", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Details summary="Edit with AI">
      <div className="flex flex-col gap-3">
        <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} maxLength={2000}
          placeholder="e.g. Make it warmer and drop the competitor jab"
          className="vt-input min-h-20" />
        <button type="button" disabled={busy || instruction.trim().length < 3} onClick={ask} className="vt-btn vt-btn-quiet self-start">
          {busy ? "Rewriting…" : "Suggest a rewrite"}
        </button>
        {error && <p role="alert" className="text-xs text-[var(--vt-blocker)]">{error}</p>}
        {proposal && (
          <div className="vt-pop flex flex-col gap-3 rounded-xl border border-line bg-raised p-3">
            <p className="whitespace-pre-wrap text-sm leading-6">{proposal.body}</p>
            {proposal.changes.length > 0 && (
              <ul className="list-disc pl-4 text-xs text-muted">{proposal.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
            )}
            {proposal.remaining.length > 0 && (
              <p className="text-xs text-[var(--vt-warning)]">Still flagged: {proposal.remaining.join("; ")}</p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => onUse(proposal.body)} className="vt-btn vt-btn-primary">
                Use this and re-check
              </button>
              <span className="text-xs text-subtle">Written by {proposal.model}</span>
            </div>
          </div>
        )}
      </div>
    </Details>
  );
}

// What each check looks at, in words a first-time reader follows: a clean result lists these, so "clean"
// says what was looked at, not only that nothing was found.
const CHECKED_PLAIN: Record<string, string> = {
  claims: "Facts, prices and offers match what the brand approved",
  tone: "It sounds like the brand",
  terminology: "Product and brand names are written the brand's way",
  messaging: "It stays on topic and implies nothing the brand wouldn't say",
  visual: "Logos and artwork are the official ones, used as allowed",
  accessibility: "Everyone can follow it: image descriptions, captions, hashtags and readable wording",
  legal: "People shown have agreed to it, AI-made images say so, and the brand's legal rules are met",
  confidentiality: "No secret codenames or private details",
};

/** The checks behind a clean result: each one that ran, and plainly, each one that ran only partly or not at all. */
export function CleanResult({ categories }: { categories?: Record<string, CategoryScore> }) {
  const status = (c: CategoryScore) => c.status ?? (c.checked ? "checked" : "not_checked");
  const all = Object.entries(categories ?? {});
  const ran = all.filter(([, c]) => status(c) === "checked");
  const simpler = all.filter(([, c]) => status(c) === "degraded");
  const skipped = all.filter(([, c]) => !["checked", "degraded"].includes(status(c)));
  const plain = (name: string) => CHECKED_PLAIN[name] ?? name;
  if (all.length === 0) {
    return <p className="rounded-2xl bg-[var(--vt-ok-bg)] px-4 py-3 text-sm font-medium text-[var(--vt-ok)]">Nothing to fix.</p>;
  }
  return (
    <div className="rounded-2xl bg-[var(--vt-ok-bg)] px-4 py-3 text-sm">
      <p className="font-medium text-[var(--vt-ok)]">Nothing to fix. Here is what was checked:</p>
      {ran.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1.5">
          {ran.map(([name]) => (
            <li key={name} className="flex gap-2">
              <span aria-hidden className="text-[var(--vt-ok)]">✓</span>
              <span className="text-ink">{plain(name)}</span>
            </li>
          ))}
        </ul>
      )}
      {simpler.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Checked only with simple word matching, without AI, this time: {simpler.map(([n]) => plain(n).toLowerCase()).join("; ")}.
        </p>
      )}
      {skipped.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Not checked: {skipped.map(([n, c]) => `${plain(n).toLowerCase()} (${(COVERAGE_LABEL[status(c)]?.text ?? "not checked").toLowerCase()})`).join("; ")}.
        </p>
      )}
    </div>
  );
}

export function CoverageTag({ category: c }: { category: CategoryScore }) {
  const label = COVERAGE_LABEL[c.status ?? (c.checked ? "checked" : "not_checked")];
  if (!label) return <span className="text-muted">{c.findings} finding{c.findings === 1 ? "" : "s"}</span>;
  return <span className={`font-semibold ${label.tone}`}>{label.text}</span>;
}

/** Maps a code point offset to a UTF-16 index in `text`. */
export function utf16Index(text: string): (cp: number) => number {
  const starts: number[] = [];
  let i = 0;
  for (const ch of text) {
    starts.push(i);
    i += ch.length;
  }
  starts.push(i);
  return (cp) => starts[Math.min(Math.max(cp, 0), starts.length - 1)];
}

export function findingKey(f: Finding): string {
  return `${f.category}|${f.source ?? "body"}|${f.quote ?? f.title}`;
}

export function HighlightedBody({ body, findings, active, onSelect, innerRef, replaced = {}, kept, leaving = null }: {
  body: string;
  findings: Finding[];
  active: number | null;
  onSelect: (id: number) => void;
  innerRef: React.RefObject<HTMLElement | null>;
  /** Fixes asked for or chosen, by finding id: the fix's own words are swapped inside the flagged span, as the
   * backend will splice them, so the text reads as it will go out. */
  replaced?: Record<number, { original: string; proposed: string }>;
  /** Findings kept as they are or ticked off: still marked, quietly. */
  kept?: Set<number>;
  /** The finding whose decision is being saved; its words fade out before the new ones arrive. */
  leaving?: number | null;
}) {
  // The API counts characters in code points; JS strings index UTF-16 units,
  // so every emoji before a span would shift it by one. Convert first.
  const at = utf16Index(body);
  findings = findings.map((f) => f.span_start == null || f.span_end == null ? f
    : { ...f, span_start: at(f.span_start), span_end: at(f.span_end) });
  // Overlapping spans keep the most severe finding; the others still appear in the checklist.
  const spans = findings
    .filter((f) => f.span_start != null && f.span_end != null && f.span_end > f.span_start)
    .sort((a, b) => a.span_start! - b.span_start! || LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level));
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const f of spans) {
    if (f.span_start! < cursor) continue;
    if (f.span_start! > cursor) parts.push(body.slice(cursor, f.span_start!));
    const swap = replaced[f.id];
    const span = body.slice(f.span_start!, f.span_end!);
    // A fix whose words are not in the span is one the backend would skip; show the words unchanged then.
    const at = swap ? span.indexOf(swap.original) : -1;
    if (swap && at >= 0 && leaving !== f.id) {
      parts.push(
        <span key={f.id}>
          {span.slice(0, at)}
          <ins data-id={f.id} data-active={active === f.id} className="vt-fix" title="Asked-for wording" tabIndex={0} role="button"
            aria-label={`Fix for: ${f.title}`} onClick={() => onSelect(f.id)}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(f.id))}>
            {swap.proposed || <span className="text-subtle">(removed)</span>}
          </ins>
          {span.slice(at + swap.original.length)}
        </span>,
      );
      cursor = f.span_end!;
      continue;
    }
    parts.push(
      <mark key={f.id} data-id={f.id} data-level={f.level} data-active={active === f.id} tabIndex={0} role="button"
        data-kept={kept?.has(f.id) || undefined} data-leaving={leaving === f.id || undefined}
        aria-label={`${f.level}: ${f.title}`} onClick={() => onSelect(f.id)}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(f.id))}>
        {body.slice(f.span_start!, f.span_end!)}
      </mark>,
    );
    cursor = f.span_end!;
  }
  parts.push(body.slice(cursor));
  return <p ref={innerRef as React.RefObject<HTMLParagraphElement>} className="whitespace-pre-wrap text-[15px] leading-8">{parts}</p>;
}

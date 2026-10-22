"use client";

import { useState } from "react";
import { createRule, extractRules, upload } from "@/lib/review-client";
import type { RuleDraft } from "@/lib/types";
import { UploadIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Field } from "./parts";

const DOC_TYPES = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const SEVERITY_TONE = { must: "blocker", should: "warning", may: "muted" } as const;

type Proposal = RuleDraft & { keep: boolean };

/**
 * Brand book in, draft rules out. Verytas reads the guidelines (a model when one
 * is configured, a plainer offline reading otherwise) and proposes one rule per
 * instruction. Nothing is saved until the admin keeps proposals; kept ones are
 * added as drafts, which no review uses until someone activates them.
 */
export function ImportTab({ onAdded }: { onAdded: () => void }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("");
  const [phase, setPhase] = useState<"idle" | "reading" | "review" | "adding">("idle");
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [notes, setNotes] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const toast = useToast();

  async function read() {
    setPhase("reading");
    try {
      const blob = file ? await upload(file) : null;
      const out = await extractRules({ text: blob ? undefined : text, blob_id: blob?.id, source_ref: source.trim() || file?.name || undefined });
      setProposals(out.rules.map((r) => ({ ...r, keep: true })));
      setNotes(out.notes);
      setModel(out.model);
      setPhase("review");
      if (out.rules.length === 0) toast({ kind: "info", title: "No checkable instructions found", detail: "Try the section with the do's and don'ts." });
    } catch (err) {
      setPhase("idle");
      toast({ kind: "error", title: "Couldn't read the guidelines", detail: (err as Error).message });
    }
  }

  async function add() {
    setPhase("adding");
    const kept = proposals.filter((p) => p.keep);
    let added = 0;
    const failed: string[] = [];
    // One at a time: codes were chosen to be unique, and a clash should fail alone, not the batch.
    for (const p of kept) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { keep, ...rule } = p;
      try {
        await createRule(rule);
        added++;
      } catch (err) {
        failed.push(`${p.code}: ${(err as Error).message}`);
      }
    }
    toast({ kind: failed.length ? "warning" : "success", title: `${added} draft rule${added === 1 ? "" : "s"} added`,
      detail: failed.length ? `${failed.length} skipped. ${failed[0]}` : "Find them under Rules, Drafts. Activate each when it reads right." });
    setProposals([]);
    setText("");
    setFile(null);
    setPhase("idle");
    onAdded();
  }

  const set = (i: number, p: Partial<Proposal>) => setProposals((xs) => xs.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const kept = proposals.filter((p) => p.keep).length;

  if (phase === "review" || phase === "adding") {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm"><span className="font-semibold">{proposals.length}</span> proposed rule{proposals.length === 1 ? "" : "s"}
            <span className="text-muted"> · read by {model.startsWith("offline") ? "the offline reader" : <code>{model}</code>}</span></p>
          <div className="ml-auto flex gap-2">
            <button type="button" onClick={() => { setProposals([]); setPhase("idle"); }} className="vt-btn vt-btn-quiet py-1.5">Start over</button>
            <button type="button" disabled={phase === "adding" || kept === 0} onClick={add} className="vt-btn vt-btn-primary py-1.5">
              {phase === "adding" ? "Adding..." : `Add ${kept} as drafts`}
            </button>
          </div>
        </div>
        {notes.length > 0 && <ul className="rounded-xl bg-[var(--vt-warning-bg)] px-4 py-2.5 text-xs text-[var(--vt-warning)]">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
        <ul className="overflow-hidden rounded-xl border border-line bg-raised">
          {proposals.map((p, i) => (
            <li key={p.code} className={`grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3 border-b border-line px-4 py-3 last:border-0 ${p.keep ? "" : "opacity-55"}`}>
              <input type="checkbox" checked={p.keep} onChange={(e) => set(i, { keep: e.target.checked })} aria-label={`Keep ${p.title}`}
                className="mt-1 h-4 w-4 accent-[var(--vt-accent)]" />
              <div className="flex min-w-0 flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <input value={p.title} onChange={(e) => set(i, { title: e.target.value })} aria-label="Title" maxLength={200}
                    className="min-w-0 flex-1 rounded-md bg-transparent px-1 py-0.5 text-sm font-medium outline-none hover:bg-sunken focus:bg-sunken" />
                  <select value={p.severity} onChange={(e) => set(i, { severity: e.target.value as RuleDraft["severity"] })} aria-label="Severity"
                    className="vt-input w-auto py-0.5 pr-7 text-xs">
                    <option value="must">Must</option><option value="should">Should</option><option value="may">May</option>
                  </select>
                </div>
                <p className="text-xs leading-5 text-muted">{p.text}</p>
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone={SEVERITY_TONE[p.severity]}>{p.severity}</Badge>
                  <Badge>{p.category}</Badge>
                  <Badge tone={p.kind === "deterministic" ? "accent" : "muted"}>{p.kind === "deterministic" ? "exact match" : "judged by the model"}</Badge>
                  <code className="text-[11px] text-subtle">{p.code}</code>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <section className="vt-card flex flex-col gap-4 p-4 md:p-5" aria-label="Import a brand book">
      <div>
        <h3 className="text-sm font-semibold">Import a brand book</h3>
        <p className="mt-1 text-xs text-muted">Paste the guidelines or upload the PDF or Word file. You review every proposal before anything is added.</p>
      </div>
      <Field label="Guidelines text">
        <textarea value={text} onChange={(e) => setText(e.target.value)} disabled={file != null} maxLength={200_000}
          placeholder={'Always write in a warm, plain voice.\nNever promise results we can\'t prove.\nSay "sign in", not "login".'}
          className="vt-input min-h-40 text-sm" />
      </Field>
      <div className="flex flex-wrap items-end gap-3">
        <label className="vt-btn vt-btn-quiet cursor-pointer">
          <UploadIcon size={14} /> {file ? file.name.slice(0, 32) : "Or upload PDF / Word"}
          <input type="file" accept={DOC_TYPES} className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {file && <button type="button" onClick={() => setFile(null)} className="text-xs text-muted hover:text-ink">Remove file</button>}
        <Field label="Source" hint="shown on every rule" className="min-w-48 flex-1">
          <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="Brand book 2026, v3" maxLength={300} className="vt-input" />
        </Field>
        <button type="button" disabled={phase === "reading" || (!file && !text.trim())} onClick={read} className="vt-btn vt-btn-primary">
          {phase === "reading" ? "Reading..." : "Propose rules"}
        </button>
      </div>
    </section>
  );
}

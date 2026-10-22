"use client";

import { useState } from "react";
import { createTerm, deleteTerm, updateTerm } from "@/lib/review-client";
import type { Term } from "@/lib/types";
import { PlusIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field, today } from "./parts";

/**
 * Codenames and unreleased names. A post that mentions one is blocked, and the
 * term is redacted from anything sent to a model, in text and in image pixels.
 * Past its embargo date a term is public and stops being guarded.
 */
export function TermsTab({ terms, onChanged }: { terms: Term[]; onChanged: () => void }) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ term: "", note: "", embargo_until: "" });
  const [editing, setEditing] = useState<number | null>(null);
  const [removing, setRemoving] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const on = today();

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try {
      await fn();
      toast({ kind: "success", title: done });
      onChanged();
      return true;
    } catch (err) {
      toast({ kind: "error", title: "Couldn't save", detail: (err as Error).message });
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <p className="text-xs text-muted">Only brand admins see this list. The audit log records changes, never the terms.</p>
        <button type="button" onClick={() => setAdding(true)} className="vt-btn vt-btn-primary ml-auto py-1.5"><PlusIcon size={14} /> Add term</button>
      </div>
      {adding && (
        <section className="vt-pop vt-card grid gap-3 p-4 md:grid-cols-[1fr_1fr_10rem_auto] md:items-end" aria-label="Add term">
          <Field label="Term"><input value={draft.term} onChange={(e) => setDraft({ ...draft, term: e.target.value })} placeholder="Project Lumen" className="vt-input" /></Field>
          <Field label="Note" hint="optional"><input value={draft.note} onChange={(e) => setDraft({ ...draft, note: e.target.value })} placeholder="Q1 launch codename" className="vt-input" /></Field>
          <Field label="Public from" hint="optional"><input type="date" value={draft.embargo_until} onChange={(e) => setDraft({ ...draft, embargo_until: e.target.value })} className="vt-input" /></Field>
          <div className="flex gap-2">
            <button type="button" disabled={busy || draft.term.trim().length < 2} className="vt-btn vt-btn-primary"
              onClick={async () => {
                const ok = await act(() => createTerm({ term: draft.term.trim(), note: draft.note.trim() || null, embargo_until: draft.embargo_until || null }), "Term guarded");
                if (ok) { setDraft({ term: "", note: "", embargo_until: "" }); setAdding(false); }
              }}>Add</button>
            <button type="button" onClick={() => setAdding(false)} className="vt-btn vt-btn-quiet">Cancel</button>
          </div>
        </section>
      )}
      {terms.length === 0 ? <Empty>No confidential terms. Add codenames and unreleased product names here.</Empty> : (
        <ul className="overflow-hidden rounded-xl border border-line bg-raised">
          {terms.map((t) => {
            const lifted = t.embargo_until != null && t.embargo_until <= on;
            return (
              <li key={t.id} className="border-b border-line px-4 py-3 last:border-0">
                {editing === t.id ? (
                  <TermEdit term={t} busy={busy} onCancel={() => setEditing(null)}
                    onSave={async (p) => { if (await act(() => updateTerm(t.id, p), "Term updated")) setEditing(null); }} />
                ) : (
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{t.term}</p>
                      <p className="truncate text-[11px] text-subtle">{t.note ?? "No note"}{t.embargo_until ? ` · public from ${t.embargo_until}` : ""}</p>
                    </div>
                    <Badge tone={lifted ? "muted" : "blocker"}>{lifted ? "Embargo lifted" : "Guarded"}</Badge>
                    {removing === t.id ? (
                      <span className="vt-pop flex items-center gap-1.5 text-xs">
                        <span className="text-[var(--vt-blocker)]">Stop guarding it?</span>
                        <button type="button" disabled={busy} onClick={async () => { if (await act(() => deleteTerm(t.id), "Term removed")) setRemoving(null); }}
                          className="vt-btn px-2 py-1 text-xs text-[var(--vt-blocker)]">Remove</button>
                        <button type="button" onClick={() => setRemoving(null)} className="vt-btn vt-btn-quiet px-2 py-1 text-xs">Keep</button>
                      </span>
                    ) : (
                      <span className="flex gap-1.5">
                        <button type="button" onClick={() => setEditing(t.id)} className="vt-btn vt-btn-quiet px-2.5 py-1 text-xs">Edit</button>
                        <button type="button" onClick={() => setRemoving(t.id)} className="vt-btn px-2.5 py-1 text-xs text-subtle hover:text-[var(--vt-blocker)]">Remove</button>
                      </span>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function TermEdit({ term, busy, onSave, onCancel }: { term: Term; busy: boolean; onSave: (p: Partial<Term>) => void; onCancel: () => void }) {
  const [note, setNote] = useState(term.note ?? "");
  const [date, setDate] = useState(term.embargo_until ?? "");
  return (
    <div className="grid gap-3 md:grid-cols-[1fr_10rem_auto] md:items-end">
      <Field label={`Note for ${term.term}`}><input value={note} onChange={(e) => setNote(e.target.value)} className="vt-input" /></Field>
      <Field label="Public from"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="vt-input" /></Field>
      <div className="flex gap-2">
        <button type="button" disabled={busy} onClick={() => onSave({ note: note.trim() || null, embargo_until: date || null })} className="vt-btn vt-btn-primary">Save</button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet">Cancel</button>
      </div>
    </div>
  );
}

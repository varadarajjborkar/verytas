"use client";

import { useState } from "react";
import { createFact, retireFact } from "@/lib/review-client";
import type { Fact } from "@/lib/types";
import { PlusIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field, today } from "./parts";

type Window = "current" | "scheduled" | "expired" | "withdrawn";

function windowOf(f: Fact, on: string): Window {
  if (!f.approved) return "withdrawn";
  if (f.valid_from > on) return "scheduled";
  if (f.valid_to && f.valid_to <= on) return "expired";
  return "current";
}
const WINDOW: Record<Window, { label: string; tone: "ok" | "accent" | "muted" }> = {
  current: { label: "Valid today", tone: "ok" },
  scheduled: { label: "Starts later", tone: "accent" },
  expired: { label: "Expired", tone: "muted" },
  withdrawn: { label: "Withdrawn", tone: "muted" },
};

/**
 * Approved facts with the dates they hold for. A claim in a post is checked
 * against the fact valid on the day; an outdated figure is flagged with the
 * current one. Replacing a figure closes the old one's window where the new opens.
 */
export function FactsTab({ facts, editable, onChanged }: { facts: Fact[]; editable: boolean; onChanged: () => void }) {
  const [form, setForm] = useState<Partial<Fact> | null>(null);
  const [showOld, setShowOld] = useState(false);
  const toast = useToast();
  const on = today();
  const shown = facts.filter((f) => showOld || ["current", "scheduled"].includes(windowOf(f, on)))
    .sort((a, b) => (a.subject ?? "").localeCompare(b.subject ?? "") || b.valid_from.localeCompare(a.valid_from));

  const retire = async (f: Fact) => {
    try {
      await retireFact(f.id);
      toast({ kind: "success", title: "Fact retired", detail: "It no longer backs claims from today." });
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't retire the fact", detail: (err as Error).message });
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-muted">
          <input type="checkbox" checked={showOld} onChange={(e) => setShowOld(e.target.checked)} className="h-4 w-4 accent-[var(--vt-accent)]" />
          Show expired and withdrawn
        </label>
        {editable && (
          <button type="button" onClick={() => setForm({ valid_from: on, tier: "public" })} className="vt-btn vt-btn-primary ml-auto py-1.5">
            <PlusIcon size={14} /> New fact
          </button>
        )}
      </div>
      {form && <FactForm initial={form} onCancel={() => setForm(null)} onDone={() => { setForm(null); onChanged(); }} />}
      {shown.length === 0 ? <Empty>No facts yet. Add the figures and statements posts are allowed to cite.</Empty> : (
        <ul className="overflow-hidden rounded-xl border border-line bg-raised">
          {shown.map((f) => {
            const w = windowOf(f, on);
            return (
              <li key={f.id} className="flex flex-col gap-2 border-b border-line px-4 py-3 last:border-0 md:flex-row md:items-center md:gap-4">
                <div className="min-w-0 flex-1">
                  <p className={`text-sm ${w === "expired" || w === "withdrawn" ? "text-muted line-through decoration-1" : "font-medium"}`}>{f.statement}</p>
                  <p className="mt-0.5 truncate text-[11px] text-subtle">
                    {f.subject ? `${f.subject} · ` : ""}{f.value != null ? `${f.value}${f.unit ? ` ${f.unit}` : ""} · ` : ""}
                    {f.valid_from} to {f.valid_to ?? "open"} · {f.source_ref}
                  </p>
                </div>
                <Badge tone={WINDOW[w].tone}>{WINDOW[w].label}</Badge>
                {editable && (w === "current" || w === "scheduled") && (
                  <div className="flex shrink-0 gap-1.5">
                    <button type="button" className="vt-btn vt-btn-quiet px-2.5 py-1 text-xs"
                      onClick={() => setForm({ statement: f.statement, value: f.value, unit: f.unit, subject: f.subject, tier: f.tier,
                        source_ref: "", valid_from: on > f.valid_from ? on : nextDay(f.valid_from), supersedes_id: f.id })}>
                      Update figure
                    </button>
                    <button type="button" onClick={() => retire(f)} className="vt-btn px-2.5 py-1 text-xs text-subtle hover:text-[var(--vt-blocker)]">Retire</button>
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

const nextDay = (d: string) => new Date(new Date(`${d}T00:00:00Z`).getTime() + 86_400_000).toISOString().slice(0, 10);

function FactForm({ initial, onCancel, onDone }: { initial: Partial<Fact>; onCancel: () => void; onDone: () => void }) {
  const [f, setF] = useState<Partial<Fact>>(initial);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const set = (p: Partial<Fact>) => setF((x) => ({ ...x, ...p }));
  const replacing = initial.supersedes_id != null;

  async function save() {
    setBusy(true);
    try {
      await createFact({ ...f, statement: f.statement?.trim(), source_ref: f.source_ref?.trim(), unit: f.unit?.trim() || null,
        subject: f.subject?.trim() || null, valid_to: f.valid_to || null });
      toast({ kind: "success", title: replacing ? "Figure updated" : "Fact added" });
      onDone();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't save the fact", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="vt-pop vt-card flex flex-col gap-3 p-4" aria-label={replacing ? "Update figure" : "New fact"}>
      {replacing && <p className="text-xs text-muted">The current figure stays on record and stops being valid the day this one starts.</p>}
      <Field label="Statement" hint="as a post may say it">
        <input value={f.statement ?? ""} onChange={(e) => set({ statement: e.target.value })} placeholder="TutorNest serves 1.2 million learners" className="vt-input" />
      </Field>
      <div className="grid gap-3 md:grid-cols-4">
        <Field label="Subject"><input value={f.subject ?? ""} onChange={(e) => set({ subject: e.target.value })} placeholder="learners" className="vt-input" /></Field>
        <Field label="Value"><input type="number" value={f.value ?? ""} onChange={(e) => set({ value: e.target.value === "" ? null : Number(e.target.value) })} className="vt-input" /></Field>
        <Field label="Unit"><input value={f.unit ?? ""} onChange={(e) => set({ unit: e.target.value })} placeholder="million" className="vt-input" /></Field>
        <Field label="Who may cite it">
          <select value={f.tier ?? "public"} onChange={(e) => set({ tier: e.target.value as Fact["tier"] })} className="vt-input">
            <option value="public">Public posts</option><option value="internal">Internal and above</option><option value="confidential">Confidential only</option>
          </select>
        </Field>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Source"><input value={f.source_ref ?? ""} onChange={(e) => set({ source_ref: e.target.value })} placeholder="Annual report 2026, p.4" className="vt-input" /></Field>
        <Field label="Valid from"><input type="date" value={f.valid_from ?? ""} onChange={(e) => set({ valid_from: e.target.value })} className="vt-input" /></Field>
        <Field label="Valid until" hint="optional"><input type="date" value={f.valid_to ?? ""} onChange={(e) => set({ valid_to: e.target.value || null })} className="vt-input" /></Field>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" disabled={busy || !f.statement?.trim() || !f.source_ref?.trim() || !f.valid_from} onClick={save}
          className="vt-btn vt-btn-primary py-1.5">{replacing ? "Save new figure" : "Add fact"}</button>
        <button type="button" onClick={onCancel} className="vt-btn vt-btn-quiet py-1.5">Cancel</button>
      </div>
    </section>
  );
}

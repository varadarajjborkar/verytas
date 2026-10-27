"use client";

import { useState } from "react";
import { addContact, retireContact } from "@/lib/review-client";
import type { PublicContact } from "@/lib/types";
import { PlusIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field } from "./parts";

const KIND: Record<PublicContact["kind"], { label: string; placeholder: string }> = {
  phone: { label: "Phone", placeholder: "+91 80 4567 8900" },
  email: { label: "Email", placeholder: "support@yourbrand.com, or *@yourbrand.com for the domain" },
  handle: { label: "Social handle", placeholder: "@yourbrand" },
  url: { label: "Website", placeholder: "yourbrand.com" },
};

/**
 * The contact details the company publishes. A phone number or address in a post
 * that is not listed here is flagged as private data, and a message to the brand
 * team that carries one is marked for them: one register serves both checks.
 */
export function ContactsTab({ contacts, editable, onChanged }: { contacts: PublicContact[]; editable: boolean; onChanged: () => void }) {
  const [draft, setDraft] = useState({ kind: "phone" as PublicContact["kind"], value: "", label: "", source_ref: "" });
  const [busy, setBusy] = useState<number | "add" | null>(null);
  const toast = useToast();
  const active = contacts.filter((c) => c.active);

  const add = async () => {
    setBusy("add");
    try {
      await addContact({ ...draft, value: draft.value.trim(), label: draft.label.trim() || null, source_ref: draft.source_ref.trim() || null });
      toast({ kind: "success", title: "Contact listed", detail: "Posts and messages may now carry it." });
      setDraft({ ...draft, value: "", label: "", source_ref: "" });
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't list it", detail: (err as Error).message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-2xl text-xs leading-5 text-muted">
        Only these may appear in a post. Any other phone number or address is treated as someone&apos;s private data: posts are
        flagged, and messages to the brand team that share one are marked for you to look at.
      </p>
      {editable && (
        <section className="vt-card grid gap-3 p-5 md:grid-cols-[9rem_1fr_12rem_auto] md:items-end" aria-label="Add a contact">
          <Field label="Kind">
            <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as PublicContact["kind"] })} className="vt-input">
              {(Object.keys(KIND) as PublicContact["kind"][]).map((k) => <option key={k} value={k}>{KIND[k].label}</option>)}
            </select>
          </Field>
          <Field label="Value"><input value={draft.value} onChange={(e) => setDraft({ ...draft, value: e.target.value })} placeholder={KIND[draft.kind].placeholder} className="vt-input" /></Field>
          <Field label="Label" hint="optional"><input value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} placeholder="Learner support" className="vt-input" /></Field>
          <button type="button" disabled={busy === "add" || draft.value.trim().length < 3} onClick={add} className="vt-btn vt-btn-primary"><PlusIcon size={14} /> List it</button>
        </section>
      )}
      {active.length === 0 ? <Empty>No public contacts yet. Until you add some, every phone number in a post is flagged.</Empty> : (
        <ul className="overflow-hidden rounded-xl border border-line bg-raised">
          {active.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 last:border-0">
              <Badge>{KIND[c.kind].label}</Badge>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium tabular-nums">{c.value}</p>
                <p className="truncate text-[11px] text-subtle">{c.label ?? "No label"}{c.source_ref ? ` · ${c.source_ref}` : ""}</p>
              </div>
              {editable && (
                <button type="button" disabled={busy === c.id} className="vt-btn vt-btn-xs text-subtle hover:text-[var(--vt-blocker)]"
                  onClick={async () => {
                    setBusy(c.id);
                    try {
                      await retireContact(c.id);
                      onChanged();
                    } catch (err) {
                      toast({ kind: "error", title: "Couldn't retire it", detail: (err as Error).message });
                    } finally {
                      setBusy(null);
                    }
                  }}>Retire</button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

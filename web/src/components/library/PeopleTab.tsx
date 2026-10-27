"use client";

import { useRef, useState } from "react";
import { addApproved, addReference, patchApproved, referenceUrl, removeReference } from "@/lib/review-client";
import type { ApprovedPerson, BrandEvent } from "@/lib/types";
import { CloseIcon, PlusIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field, toList, today } from "./parts";

const KIND: Record<ApprovedPerson["kind"], string> = {
  celebrity: "Celebrity", ambassador: "Ambassador", creator: "Creator", staff: "Staff", other: "Other",
};

type Standing = { label: string; tone: "ok" | "warning" | "blocker" | "muted" };

/** Where an agreement stands today, as a review would read it. */
function standing(p: ApprovedPerson, on: string): Standing {
  if (!p.active) return { label: "Turned off", tone: "muted" };
  if (p.valid_from > on) return { label: "Starts later", tone: "warning" };
  if (p.valid_to && p.valid_to <= on) return { label: "Ended", tone: "blocker" };
  return { label: "In force", tone: "ok" };
}

const fmt = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });

/** A photo made small enough to send (long side 1024 px, JPEG), read as base64 without the data: prefix. */
async function shrink(file: File): Promise<{ media_type: string; data_base64: string }> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1024 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return { media_type: "image/jpeg", data_base64: canvas.toDataURL("image/jpeg", 0.9).split(",", 2)[1] };
}

/**
 * The people the brand may show: ambassadors, celebrities with a contract, staff, and creators who appear in
 * their own posts. A face in content is compared with these photos; someone recognised but not listed, or
 * outside their dates or channels, is a blocker, because using a likeness without an agreement is a legal risk.
 */
export function PeopleTab({ people, events, editable, onChanged }: {
  people: ApprovedPerson[]; events: BrandEvent[]; editable: boolean; onChanged: () => void;
}) {
  const blank = { name: "", kind: "ambassador" as ApprovedPerson["kind"], channels: "", valid_from: today(), valid_to: "", notes: "" };
  const [draft, setDraft] = useState(blank);
  const [photo, setPhoto] = useState<File | null>(null);
  const addPicker = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const on = today();
  const eventName = new Map(events.map((e) => [e.id, e.name]));

  const add = async () => {
    setBusy("add");
    try {
      const made = await addApproved({
        name: draft.name.trim(), kind: draft.kind, channels: toList(draft.channels), valid_from: draft.valid_from,
        valid_to: draft.valid_to || null, notes: draft.notes.trim() || null,
      });
      if (photo) await addReference(made.id, await shrink(photo));
      toast({ kind: "success", title: `${made.name} added`, detail: photo ? "Their photo is what faces in posts are compared with." : "Add a photo so faces in posts can be matched to them." });
      setDraft(blank);
      setPhoto(null);
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't add them", detail: (err as Error).message });
    } finally {
      setBusy(null);
    }
  };

  const act = async (key: string, work: () => Promise<unknown>, failed: string) => {
    setBusy(key);
    try { await work(); onChanged(); }
    catch (err) { toast({ kind: "error", title: failed, detail: (err as Error).message }); }
    finally { setBusy(null); }
  };

  const valid = draft.name.trim().length > 0 && Boolean(draft.valid_from) && (!draft.valid_to || draft.valid_to > draft.valid_from);
  const sorted = [...people].sort((a, b) => Number(b.active) - Number(a.active) || a.name.localeCompare(b.name));

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-2xl text-xs leading-5 text-muted">
        Who may appear in the brand&apos;s content, and on what terms. Faces in images and videos are compared with these
        photos. Someone recognised but not listed, or outside their dates or channels, is a must-fix: a likeness used without
        an agreement is a legal risk. Creators who appear in their own posts can add themselves from their side.
      </p>
      {editable && (
        <section className="vt-card grid gap-3 p-5 md:grid-cols-2 xl:grid-cols-[1.4fr_9rem_1fr_9rem_9rem]" aria-label="Add a person">
          <Field label="Name"><input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Full name, as people know them" className="vt-input" /></Field>
          <Field label="Who they are">
            <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as ApprovedPerson["kind"] })} className="vt-input">
              {(Object.keys(KIND) as ApprovedPerson["kind"][]).map((k) => <option key={k} value={k}>{KIND[k]}</option>)}
            </select>
          </Field>
          <Field label="Channels" hint="empty means all"><input value={draft.channels} onChange={(e) => setDraft({ ...draft, channels: e.target.value })} placeholder="For example: instagram, youtube" className="vt-input" /></Field>
          <Field label="Agreement from"><input type="date" value={draft.valid_from} onChange={(e) => setDraft({ ...draft, valid_from: e.target.value })} className="vt-input" /></Field>
          <Field label="Until" hint="optional"><input type="date" value={draft.valid_to} min={draft.valid_from} onChange={(e) => setDraft({ ...draft, valid_to: e.target.value })} className="vt-input" /></Field>
          <Field label="Notes" hint="only brand admins see these" className="md:col-span-2 xl:col-span-3">
            <input value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} placeholder="Contract ref, fee terms, usage limits" className="vt-input" />
          </Field>
          <div className="flex flex-col gap-1.5 text-xs font-medium">
            <span>Reference photo <span className="font-normal text-subtle">a clear face</span></span>
            <input ref={addPicker} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
              onChange={(e) => { setPhoto(e.target.files?.[0] ?? null); e.target.value = ""; }} />
            <span className="flex min-w-0 items-center gap-1.5">
              <button type="button" onClick={() => addPicker.current?.click()} className="vt-btn vt-btn-quiet h-9 shrink-0 text-xs">
                {photo ? "Change" : "Choose photo"}
              </button>
              {photo && (
                <span className="flex min-w-0 items-center gap-1 font-normal text-muted">
                  <span className="truncate">{photo.name}</span>
                  <button type="button" aria-label="Remove the photo" onClick={() => setPhoto(null)} className="shrink-0 hover:text-ink"><CloseIcon size={12} /></button>
                </span>
              )}
            </span>
          </div>
          <div className="flex items-end">
            <button type="button" disabled={!valid || busy === "add"} onClick={add} className="vt-btn vt-btn-primary w-full justify-center">
              <PlusIcon size={14} /> {busy === "add" ? "Adding..." : "Add person"}
            </button>
          </div>
        </section>
      )}
      {sorted.length === 0 ? (
        <Empty>No one is listed yet. Until someone is, any recognisable face in a post is flagged for the brand team to check.</Empty>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {sorted.map((p) => (
            <PersonCard key={p.id} p={p} standing={standing(p, on)} editable={editable} busy={busy} eventName={eventName}
              onPhoto={(file) => act(`photo-${p.id}`, async () => addReference(p.id, await shrink(file)), "Couldn't add the photo")}
              onRemovePhoto={(ref) => act(`ref-${ref}`, () => removeReference(p.id, ref), "Couldn't remove the photo")}
              onUntil={(d) => act(`until-${p.id}`, () => patchApproved(p.id, { valid_to: d || null }), "Couldn't change the end date")}
              onActive={(a) => act(`active-${p.id}`, () => patchApproved(p.id, { active: a }), "Couldn't change it")} />
          ))}
        </ul>
      )}
    </div>
  );
}

function PersonCard({ p, standing: st, editable, busy, eventName, onPhoto, onRemovePhoto, onUntil, onActive }: {
  p: ApprovedPerson; standing: Standing; editable: boolean; busy: string | null; eventName: Map<number, string>;
  onPhoto: (f: File) => void; onRemovePhoto: (ref: number) => void; onUntil: (d: string) => void; onActive: (a: boolean) => void;
}) {
  const picker = useRef<HTMLInputElement>(null);
  const [until, setUntil] = useState(p.valid_to ?? "");
  const refs = p.references.filter((r) => r.approved);
  return (
    <li className={`vt-card flex flex-col gap-3 p-4 ${p.active ? "" : "opacity-70"}`}>
      <div className="flex items-start gap-3">
        {refs[0] ? (
          // eslint-disable-next-line @next/next/no-img-element -- served by the API behind the session
          <img src={referenceUrl(p.id, refs[0].id)} alt="" className="h-12 w-12 shrink-0 rounded-full border border-line object-cover" />
        ) : (
          <span aria-hidden className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-sunken text-sm font-semibold text-muted">
            {p.name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase()}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-semibold">{p.name}</span>
            <Badge>{KIND[p.kind]}</Badge>
            <Badge tone={st.tone}>{st.label}</Badge>
          </p>
          <p className="mt-1 text-xs text-muted">
            From {fmt(p.valid_from)}{p.valid_to ? ` until ${fmt(p.valid_to)}` : ", no end date"}
          </p>
          <p className="mt-0.5 text-xs text-subtle">
            {p.channels.length ? p.channels.join(", ") : "Every channel"}
            {p.event_ids.length ? ` · ${p.event_ids.map((id) => eventName.get(id) ?? `campaign ${id}`).join(", ")}` : " · every campaign"}
          </p>
          {p.notes && <p className="mt-1 text-xs text-muted [overflow-wrap:anywhere]">{p.notes}</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {refs.map((r) => (
          <span key={r.id} className="group relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- served by the API behind the session */}
            <img src={referenceUrl(p.id, r.id)} alt={`Reference photo of ${p.name}`} className="h-14 w-14 rounded-lg border border-line object-cover" />
            {editable && (
              <button type="button" aria-label="Remove this photo" disabled={busy === `ref-${r.id}`} onClick={() => onRemovePhoto(r.id)}
                className="absolute -right-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full border border-line bg-raised text-muted opacity-0 shadow-sm transition-opacity hover:text-[var(--vt-blocker)] group-hover:opacity-100 focus:opacity-100 [@media(hover:none)]:opacity-100">
                <CloseIcon size={11} />
              </button>
            )}
          </span>
        ))}
        {refs.length === 0 && <span className="text-xs text-[var(--vt-warning)]">No photo yet: faces can&apos;t be matched to them.</span>}
        {editable && (
          <>
            <input ref={picker} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) onPhoto(f); e.target.value = ""; }} />
            <button type="button" disabled={busy === `photo-${p.id}` || refs.length >= 8} onClick={() => picker.current?.click()}
              className="grid h-14 w-14 place-items-center rounded-lg border border-dashed border-line-strong text-muted hover:border-accent/50 hover:text-ink"
              aria-label={`Add a photo of ${p.name}`} title="Add a photo"><PlusIcon size={16} /></button>
          </>
        )}
      </div>
      {editable && (
        <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
          <Field label="Agreement until" className="min-w-0">
            <input type="date" value={until} min={p.valid_from} onChange={(e) => setUntil(e.target.value)} className="vt-input h-8 text-xs" />
          </Field>
          <button type="button" disabled={(until || null) === p.valid_to || busy === `until-${p.id}`} onClick={() => onUntil(until)}
            className="vt-btn vt-btn-quiet h-8 text-xs">Save date</button>
          <button type="button" disabled={busy === `active-${p.id}`} onClick={() => onActive(!p.active)}
            className="vt-btn vt-btn-quiet ml-auto h-8 text-xs">{p.active ? "Turn off" : "Turn back on"}</button>
        </div>
      )}
    </li>
  );
}


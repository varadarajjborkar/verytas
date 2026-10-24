"use client";

import { useEffect, useId, useRef, useState } from "react";
import { fmtBytes, listEvents, precheck, upload } from "@/lib/review-client";
import { ChevronIcon, UploadIcon } from "../Icons";
import { BRIEF_MIN, type BriefAudio, BriefBox } from "./BriefBox";
import { today } from "../library/parts";
import { useToast } from "../Toaster";
import { CHANNELS } from "@/lib/channels";
import type { BrandEvent, Precheck, UploadedMedia } from "@/lib/types";


export type Attachment = UploadedMedia & { kind: "image" | "document" | "video"; alt: string; localId: string };

export type Draft = {
  title: string;
  channel: string;
  otherChannel: string;
  tier: "public" | "internal";
  body: string;
  attachments: Attachment[];
  intent: string;
  language: string;
  aiUsed: boolean;
  irregularityReason: string;
  /** What is in the images or video, in the creator's words or a voice note: required with a video. */
  brief: string;
  briefAudio: BriefAudio | null;
  /** The brand event this piece is for, if any: its brief and hashtag then apply. */
  eventId: number | null;
};

export const emptyDraft = (body: string): Draft => ({
  title: "Launch announcement", channel: "instagram", otherChannel: "", tier: "public", body, attachments: [],
  intent: "", language: "", aiUsed: false, irregularityReason: "", brief: "", briefAudio: null, eventId: null,
});

export function channelOf(d: Draft): string {
  return d.channel === "other" ? (d.otherChannel.trim() || "other") : d.channel;
}

export function attachmentsPayload(d: Draft) {
  const by = (k: Attachment["kind"]) => d.attachments.filter((a) => a.kind === k);
  return {
    images: by("image").map((a) => ({ id: a.localId, alt: a.alt || null, blob_id: a.id,
      media_type: ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(a.media_type) ? a.media_type : "image/png" })),
    documents: by("document").map((a) => ({ id: a.localId, name: a.name, blob_id: a.id,
      media_type: (DOCUMENT_TYPES as readonly string[]).includes(a.media_type) ? a.media_type : "application/pdf" })),
    videos: by("video").map((a) => ({ id: a.localId, name: a.name, blob_id: a.id })),
  };
}

// The API sniffs the real type from the bytes; these are the documents review reads page by page.
const DOCUMENT_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/html",
] as const;

const KIND_OF = (type: string): Attachment["kind"] | null =>
  type.startsWith("image/") ? "image" : type.startsWith("video/") ? "video"
    : (DOCUMENT_TYPES as readonly string[]).includes(type) ? "document" : null;

const field = "vt-input";

/** A native select with its own chevron: the browser's arrow sits against the
 * right border and drifts between engines, so it is hidden and drawn inset. */
function Select({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <span className="relative block">
      <select className={`${field} cursor-pointer appearance-none pr-9`} value={value} onChange={(e) => onChange(e.target.value)}>
        {children}
      </select>
      <ChevronIcon size={16} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" />
    </span>
  );
}

export function Composer({ draft, update, onSubmit, busy, demo }: {
  draft: Draft;
  /** Functional updates, so uploads finishing out of order can't overwrite each other. */
  update: (fn: (d: Draft) => Draft) => void;
  onSubmit: () => void;
  busy: boolean;
  demo: boolean;
}) {
  const toast = useToast();
  const [uploading, setUploading] = useState<string[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [check, setCheck] = useState<Precheck | null>(null);
  const [showNotes, setShowNotes] = useState(false);
  const ids = useId();
  const counter = useRef(1);
  const set = (patch: Partial<Draft>) => update((d) => ({ ...d, ...patch }));
  const channel = CHANNELS.find((c) => c.value === draft.channel);

  // Precheck as the creator works, so an irregular upload is flagged now, not after a long scan.
  useEffect(() => {
    if (demo) return;
    const t = setTimeout(() => {
      precheck({ channel: channelOf(draft), body: draft.body, attachments: attachmentsPayload(draft) })
        .then(setCheck).catch(() => setCheck(null));
    }, 600);
    return () => clearTimeout(t);
  }, [draft, demo]);

  async function addFiles(files: FileList | null, expect: Attachment["kind"]) {
    if (!files?.length) return;
    setUploadError(null);
    for (const file of Array.from(files)) {
      const kind = KIND_OF(file.type) ?? expect;
      setUploading((u) => [...u, file.name]);
      try {
        const media = await upload(file);
        const actual = KIND_OF(media.media_type);
        if (actual !== kind) throw new Error(`${file.name} is not a ${kind} (it reads as ${media.media_type})`);
        // A readable id from the file name ("summer-post"), unique within the draft.
        const stem = (file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "")
          || kind).slice(0, 32);
        const localId = `${stem}-${counter.current++}`;
        update((d) => ({ ...d, attachments: [...d.attachments, { ...media, kind, alt: "", localId }] }));
        toast({ kind: "success", title: `${file.name} uploaded`, detail: `${fmtBytes(media.bytes)} · ${media.media_type}` });
      } catch (err) {
        setUploadError((err as Error).message);
        toast({ kind: "error", title: `Couldn't upload ${file.name}`, detail: (err as Error).message });
      } finally {
        setUploading((u) => u.filter((n) => n !== file.name));
      }
    }
  }
  const remove = (localId: string) =>
    update((d) => ({ ...d, attachments: d.attachments.filter((a) => a.localId !== localId) }));
  const setAlt = (localId: string, alt: string) =>
    update((d) => ({ ...d, attachments: d.attachments.map((a) => (a.localId === localId ? { ...a, alt } : a)) }));
  const hasVideo = draft.attachments.some((a) => a.kind === "video");
  const hasImage = draft.attachments.some((a) => a.kind === "image");
  const briefOk = !hasVideo || draft.briefAudio !== null || draft.brief.trim().length >= BRIEF_MIN;
  const needsReason = Boolean(check?.needs_reason);
  const reasonOk = !needsReason || draft.irregularityReason.trim().length >= 15;
  const over = channel?.limit ? draft.body.length > channel.limit : false;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
      className="flex flex-col gap-4"
    >
      <label className="flex flex-col gap-1 text-xs font-medium text-muted">
        Title
        <input className={field} value={draft.title} maxLength={300} required onChange={(e) => set({ title: e.target.value })} />
      </label>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,9rem)]">
        <label className="flex flex-col gap-1 text-xs font-medium text-muted">
          Where it will be posted
          <Select value={draft.channel} onChange={(v) => set({ channel: v })}>
            {CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </Select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted">
          Audience
          <Select value={draft.tier} onChange={(v) => set({ tier: v as Draft["tier"] })}>
            <option value="public">Public</option>
            <option value="internal">Internal</option>
          </Select>
        </label>
      </div>
      <EventPicker value={draft.eventId} onChange={(eventId) => set({ eventId })} />
      {draft.channel === "other" && (
        <label className="flex flex-col gap-1 text-xs font-medium text-muted">
          Which app or channel?
          <input className={field} value={draft.otherChannel} maxLength={60} required placeholder="e.g. ShareChat, Moj, Koo, a community forum"
            onChange={(e) => set({ otherChannel: e.target.value })} />
        </label>
      )}

      <label className="flex flex-col gap-1 text-xs font-medium text-muted">
        <span className="flex justify-between">
          <span>Caption or text</span>
          <span className={over ? "font-semibold text-[var(--vt-blocker)]" : ""}>
            {draft.body.length.toLocaleString()}
            {channel?.limit ? ` / ${channel.limit.toLocaleString()}` : ""} characters
          </span>
        </span>
        <textarea className={`${field} min-h-44 resize-y leading-6`} value={draft.body} required maxLength={100000}
          onChange={(e) => set({ body: e.target.value })} placeholder="Paste the caption, post text or script exactly as it will appear" />
      </label>

      {/* min-w-0: a fieldset otherwise refuses to shrink below its content and overflows the card */}
      <fieldset className="flex min-w-0 flex-col gap-2">
        <legend className="mb-1 text-xs font-medium text-muted">Attachments</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          <DropTile id={`${ids}-img`} label="Images" hint="PNG, JPG, WebP, GIF · up to 6 MB" accept="image/png,image/jpeg,image/webp,image/gif"
            disabled={demo} onFiles={(f) => addFiles(f, "image")} />
          <DropTile id={`${ids}-doc`} label="Documents" hint="PDF, Word, PowerPoint, Excel, HTML" accept="application/pdf,.docx,.pptx,.xlsx,.html,.htm"
            disabled={demo} onFiles={(f) => addFiles(f, "document")} />
          <DropTile id={`${ids}-vid`} label="Video" hint="MP4, MOV, WebM" accept="video/mp4,video/quicktime,video/webm"
            disabled={demo} onFiles={(f) => addFiles(f, "video")} />
        </div>
        {demo && <p className="text-xs text-subtle">Uploads need the live API.</p>}
        {uploading.length > 0 && <p className="text-xs text-muted" role="status">Uploading {uploading.join(", ")}…</p>}
        {uploadError && <p className="text-xs text-[var(--vt-blocker)]" role="alert">{uploadError}</p>}
        {draft.attachments.length > 0 && (
          <ul className="flex flex-col gap-2">
            {draft.attachments.map((a) => (
              <li key={a.localId} className="vt-pop flex flex-col gap-2 rounded-xl border border-line bg-raised p-2.5">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="w-[4.5rem] shrink-0 rounded-md bg-sunken px-1.5 py-0.5 text-center text-[11px] font-medium capitalize text-muted">{a.kind}</span>
                  <span className="min-w-0 flex-1 truncate text-sm" title={a.name ?? ""}>{a.name ?? a.id}</span>
                  <span className="shrink-0 text-xs text-muted">{fmtBytes(a.bytes)}{metricText(a)}</span>
                  <button type="button" onClick={() => remove(a.localId)} className="shrink-0 rounded-md px-2 py-1 text-xs text-muted transition hover:bg-sunken hover:text-ink">
                    Remove
                  </button>
                </div>
                {a.kind === "image" && (
                  <input className={field} value={a.alt} placeholder="Alt text"
                    aria-label={`Alt text for ${a.name}`} onChange={(e) => setAlt(a.localId, e.target.value)} />
                )}
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      {needsReason && check && (
        <div className="rounded-xl bg-[var(--vt-warning-bg)] p-3" role="alert">
          <p className="text-sm font-semibold text-[var(--vt-warning)]">This upload is unusual for {CHANNELS.find((c) => c.value === draft.channel)?.label ?? channelOf(draft)}</p>
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {check.irregularities.map((i, k) => (
              <li key={k}>
                <span className="font-medium">{i.subject}: {i.value}</span> (expected {i.expected}). {i.why}
                {i.over_limit && <span className="ml-1 font-semibold text-[var(--vt-blocker)]">Over the platform limit.</span>}
              </li>
            ))}
          </ul>
          <label className="mt-3 flex flex-col gap-1 text-xs font-medium">
            Why is it this way? It is still checked in full and counts against its score.
            <textarea className={`${field} min-h-16`} value={draft.irregularityReason} maxLength={2000}
              placeholder="e.g. The marketing team asked for the full catalogue as one LinkedIn document"
              onChange={(e) => set({ irregularityReason: e.target.value })} />
          </label>
        </div>
      )}

      {(hasVideo || hasImage) && (
        <BriefBox text={draft.brief} audio={draft.briefAudio} required={hasVideo}
          onText={(brief) => set({ brief })} onAudio={(briefAudio) => set({ briefAudio })} />
      )}

      <div className="rounded-xl border border-line">
        <button type="button" onClick={() => setShowNotes((s) => !s)} aria-expanded={showNotes}
          className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm font-medium">
          <span>Context for reviewers <span className="font-normal text-subtle">optional</span></span>
          <ChevronIcon size={16} className={`text-muted transition-transform duration-200 ${showNotes ? "rotate-180" : ""}`} />
        </button>
        {showNotes && (
          <div className="vt-pop flex flex-col gap-3 border-t border-line p-3">
            <p className="text-xs text-subtle">Read only when something is flagged. It never clears a rule on its own.</p>
            <textarea className={`${field} min-h-20`} value={draft.intent} maxLength={2000}
              placeholder="e.g. 'Dhamaka' here means a big sale, not an explosion" onChange={(e) => set({ intent: e.target.value })} />
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-xs font-medium text-muted">
                Language the audience reads it in
                <input className={field} value={draft.language} maxLength={60} placeholder="e.g. Hinglish"
                  onChange={(e) => set({ language: e.target.value })} />
              </label>
              <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input type="checkbox" checked={draft.aiUsed} onChange={(e) => set({ aiUsed: e.target.checked })}
                  className="h-4 w-4 accent-[var(--vt-accent)]" />
                Generative AI was used to make part of this
              </label>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={busy || !draft.body.trim() || uploading.length > 0 || !reasonOk || !briefOk}
          className="vt-btn vt-btn-primary">
          {busy ? "Checking…" : "Run review"}
        </button>
        {!reasonOk && <span className="text-xs text-[var(--vt-warning)]">Add a reason of at least 15 characters for the unusual upload.</span>}
      </div>
    </form>
  );
}

function metricText(a: Attachment): string {
  const m = a.metrics as { duration?: number; pages?: number; width?: number; height?: number };
  if (a.kind === "video" && m.duration) return ` · ${Math.round(m.duration)} s · ${m.width}×${m.height}`;
  if (a.kind === "document" && m.pages) return ` · ${m.pages} page${m.pages === 1 ? "" : "s"}`;
  return "";
}

function DropTile({ id, label, hint, accept, disabled, onFiles }: {
  id: string; label: string; hint: string; accept: string; disabled: boolean; onFiles: (f: FileList | null) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <label htmlFor={id}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) onFiles(e.dataTransfer.files); }}
      className={`flex cursor-pointer flex-col items-center justify-center gap-1 rounded-xl border border-dashed px-3 py-4 text-center transition ${over ? "border-accent bg-accent/5" : "border-line-strong hover:border-accent/60 hover:bg-sunken/50"} ${disabled ? "pointer-events-none opacity-50" : ""}`}>
      <UploadIcon size={16} className="text-muted" />
      <span className="text-sm font-medium">{label}</span>
      <span className="text-[11px] text-subtle">{hint}</span>
      <input id={id} type="file" multiple accept={accept} disabled={disabled} className="sr-only"
        onChange={(e) => { onFiles(e.target.files); e.target.value = ""; }} />
    </label>
  );
}

/** Running and scheduled brand events a piece can be made for. Hidden when there are none. */
function EventPicker({ value, onChange }: { value: number | null; onChange: (id: number | null) => void }) {
  const [events, setEvents] = useState<BrandEvent[]>([]);
  useEffect(() => {
    let live = true;
    listEvents().then((xs) => { if (live) setEvents(xs.filter((e) => e.status === "active" && (e.live || e.starts_on > today()))); })
      .catch(() => {});
    return () => { live = false; };
  }, []);
  if (events.length === 0) return null;
  const chosen = events.find((e) => e.id === value);
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-muted">
      Made for a brand event?
      <Select value={value == null ? "" : String(value)} onChange={(v) => onChange(v ? Number(v) : null)}>
        <option value="">No, a regular post</option>
        {events.map((e) => <option key={e.id} value={e.id}>{e.name}{e.live ? " (running now)" : ` (from ${e.starts_on})`}</option>)}
      </Select>
      {chosen && (chosen.guidance || chosen.hashtags.length > 0) && (
        <span className="mt-1 rounded-lg bg-sunken px-3 py-2 text-[12px] font-normal leading-5 text-muted">
          {chosen.guidance}{chosen.hashtags.length > 0 && <> Use {chosen.hashtags.map((t) => (t.startsWith("#") ? t : `#${t}`)).join(" or ")}.</>}
        </span>
      )}
    </label>
  );
}

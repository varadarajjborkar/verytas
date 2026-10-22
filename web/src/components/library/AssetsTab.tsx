"use client";

import { useState } from "react";
import { assetImageUrl, createAsset, fmtBytes, retireAsset } from "@/lib/review-client";
import type { BrandAsset } from "@/lib/types";
import { UploadIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field } from "./parts";

const MAX_BYTES = 6 * 1024 * 1024;
const PARTS = ["full", "face", "head", "body", "wordmark", "icon"] as const;

const readBase64 = (file: File) => new Promise<string>((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result).split(",")[1] ?? "");
  r.onerror = () => reject(new Error("Couldn't read the file."));
  r.readAsDataURL(file);
});

/**
 * Official logos and mascots: the ground truth every image in every review is
 * compared with. Altered details, garbled wordmarks and look-alikes are flagged;
 * a part not registered here (a mascot's body, say) is treated as unapproved.
 */
export function AssetsTab({ assets, editable, onChanged }: { assets: BrandAsset[]; editable: boolean; onChanged: () => void }) {
  const [showRetired, setShowRetired] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const toast = useToast();
  const shown = assets.filter((a) => showRetired || a.active);

  const retire = async (a: BrandAsset) => {
    setBusy(a.id);
    try {
      await retireAsset(a.id);
      toast({ kind: "success", title: `${a.name} retired` });
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't retire it", detail: (err as Error).message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {editable && <AssetUpload onDone={onChanged} />}
      <label className="flex items-center gap-2 self-start text-xs text-muted">
        <input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} className="h-4 w-4 accent-[var(--vt-accent)]" />
        Show retired
      </label>
      {shown.length === 0 ? <Empty>No official artwork yet. Upload the logo and mascot as they may appear.</Empty> : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {shown.map((a) => (
            <li key={a.id} className={`vt-card overflow-hidden ${a.active ? "" : "opacity-60"}`}>
              <div className="grid aspect-[4/3] place-items-center bg-[repeating-conic-gradient(var(--vt-sunken)_0_25%,transparent_0_50%)] bg-[length:16px_16px] p-3">
                {/* Served by our own proxy as this person; next/image would re-fetch it without their cookie. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={assetImageUrl(a.id)} alt={`${a.name} (${a.part})`} loading="lazy" className="max-h-full max-w-full object-contain" />
              </div>
              <div className="flex flex-col gap-1 p-3">
                <p className="truncate text-sm font-medium">{a.name}</p>
                <div className="flex flex-wrap gap-1">
                  <Badge>{a.kind}</Badge><Badge>{a.part}</Badge>
                  {!a.active && <Badge tone="warning">Retired</Badge>}
                  {a.tier !== "public" && <Badge tone="accent">{a.tier}</Badge>}
                </div>
                {a.wordmark && <p className="truncate text-[11px] text-subtle">Reads &ldquo;{a.wordmark}&rdquo;</p>}
                {editable && a.active && (
                  <button type="button" disabled={busy === a.id} onClick={() => retire(a)}
                    className="mt-1 self-start text-[11px] font-medium text-subtle hover:text-[var(--vt-blocker)]">Retire</button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AssetUpload({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState({ name: "", kind: "logo" as BrandAsset["kind"], part: "full" as (typeof PARTS)[number], wordmark: "", tier: "public" as BrandAsset["tier"] });
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const tooBig = file != null && file.size > MAX_BYTES;

  async function save() {
    if (!file) return;
    setBusy(true);
    try {
      const out = await createAsset({ ...meta, name: meta.name.trim(), wordmark: meta.wordmark.trim() || null,
        media_type: file.type, data_base64: await readBase64(file) });
      toast({ kind: out.warning ? "warning" : "success", title: `${out.name} registered`, detail: out.warning ?? undefined });
      setFile(null);
      setMeta((m) => ({ ...m, name: "", wordmark: "" }));
      onDone();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't register it", detail: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="vt-card flex flex-col gap-3 p-4" aria-label="Upload artwork">
      <div className="grid gap-3 md:grid-cols-[auto_1fr_8rem_8rem] md:items-end">
        <label className="vt-btn vt-btn-quiet cursor-pointer">
          <UploadIcon size={14} /> {file ? file.name.slice(0, 24) : "Choose image"}
          <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only"
            onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); if (f && !meta.name) setMeta((m) => ({ ...m, name: f.name.replace(/\.\w+$/, "") })); }} />
        </label>
        <Field label="Name"><input value={meta.name} onChange={(e) => setMeta({ ...meta, name: e.target.value })} maxLength={120} className="vt-input" /></Field>
        <Field label="Kind">
          <select value={meta.kind} onChange={(e) => setMeta({ ...meta, kind: e.target.value as BrandAsset["kind"] })} className="vt-input">
            <option value="logo">Logo</option><option value="mascot">Mascot</option><option value="other">Other</option>
          </select>
        </Field>
        <Field label="Shows">
          <select value={meta.part} onChange={(e) => setMeta({ ...meta, part: e.target.value as (typeof PARTS)[number] })} className="vt-input capitalize">
            {PARTS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_12rem_auto] md:items-end">
        <Field label="Text in the artwork" hint="exact spelling, optional"><input value={meta.wordmark} onChange={(e) => setMeta({ ...meta, wordmark: e.target.value })} className="vt-input" /></Field>
        <Field label="Who may use it">
          <select value={meta.tier} onChange={(e) => setMeta({ ...meta, tier: e.target.value as BrandAsset["tier"] })} className="vt-input">
            <option value="public">Public posts</option><option value="internal">Internal and above</option><option value="confidential">Confidential only</option>
          </select>
        </Field>
        <button type="button" disabled={busy || !file || tooBig || !meta.name.trim()} onClick={save} className="vt-btn vt-btn-primary">
          {busy ? "Registering..." : "Register"}
        </button>
      </div>
      {tooBig && <p className="text-xs text-[var(--vt-blocker)]">That image is {fmtBytes(file.size)}; the limit is {fmtBytes(MAX_BYTES)}.</p>}
    </section>
  );
}

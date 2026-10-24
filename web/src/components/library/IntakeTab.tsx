"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { answerIntake, decideDraft, decideDrafts, getIntake, intakeUpload, listIntake, refreshIntake, startIntake } from "@/lib/review-client";
import type { IntakeBatch, IntakeBatchDetail, IntakeDraft, IntakeItem, IntakeItemIn } from "@/lib/types";
import { UploadIcon } from "../Icons";
import { useToast } from "../Toaster";
import { Badge, Empty, Field } from "./parts";

const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.csv,.tsv,.json,.txt,.md,image/*,video/*,audio/*";
const STATUS: Record<IntakeItem["status"], { label: string; tone: "muted" | "ok" | "warning" | "blocker" | "accent" }> = {
  queued: { label: "Waiting", tone: "muted" },
  reading: { label: "Reading", tone: "accent" },
  understood: { label: "Understood", tone: "ok" },
  needs_context: { label: "Needs your answer", tone: "warning" },
  failed: { label: "Couldn't read", tone: "blocker" },
};
const TARGET: Record<IntakeDraft["target"], string> = { rule: "Rules", fact: "Facts", term: "Confidential terms", asset: "Artwork" };
const ISSUE: Record<string, string> = {
  conflict: "conflicts", no_unit: "no unit", expired: "expired", open_question: "open question",
  rejected_by_library: "library refused it",
};

/** The payload field an admin may correct before approving, per kind of draft. */
const fieldOf = (t: IntakeDraft["target"]) => (t === "fact" ? "statement" : t === "rule" ? "text" : t === "term" ? "term" : "name");
const originalText = (d: IntakeDraft) => String((d.payload as Record<string, unknown>)[fieldOf(d.target)] ?? "");

type Pick = { file?: File; url?: string; text?: string; name: string; context: string };

/**
 * Prism Intake. A company hands over what it has (brand books, price sheets, decks, charts, logos,
 * recordings, a read-only link to live data); Verytas reads it, says what it understood, asks about
 * what it couldn't place, and drafts rules, facts, codenames and artwork. Nothing is added until an
 * admin approves a draft, and each draft shows where it came from.
 */
export function IntakeTab({ onAdded }: { onAdded: () => void }) {
  const [batches, setBatches] = useState<IntakeBatch[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const load = useCallback(() => listIntake().then(setBatches).catch(() => setBatches([])), []);
  useEffect(() => { void load(); }, [load]);
  return (
    <div className="flex flex-col gap-5">
      <HandOver onStarted={(id) => { setOpen(id); void load(); }} />
      {open != null && <BatchView key={open} id={open} onAdded={onAdded} onClose={() => { setOpen(null); void load(); }} />}
      {batches && batches.length > 0 && open == null && (
        <section className="vt-card p-4 md:p-5" aria-label="Earlier hand-overs">
          <h3 className="text-sm font-semibold">Earlier hand-overs</h3>
          <ul className="mt-3 flex flex-col divide-y divide-line">
            {batches.map((b) => (
              <li key={b.id}>
                <button type="button" onClick={() => setOpen(b.id)} className="flex w-full flex-wrap items-center gap-2 py-2.5 text-left text-sm hover:text-accent">
                  <span className="font-medium">#{b.id}</span>
                  <span className="min-w-0 flex-1 truncate text-muted">{b.note || "No note"}</span>
                  {b.summary.drafts && <span className="text-xs text-subtle">{Object.values(b.summary.drafts).reduce((a, n) => a + n, 0)} drafts</span>}
                  <Badge tone={b.status === "done" ? "ok" : b.status === "failed" ? "blocker" : "accent"}>{b.status}</Badge>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function HandOver({ onStarted }: { onStarted: (id: number) => void }) {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [note, setNote] = useState("");
  const [link, setLink] = useState("");
  const [paste, setPaste] = useState("");
  const [tier, setTier] = useState("internal");
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  // A file that already went up is not sent again when a later one fails and the hand-over is retried.
  const uploaded = useRef(new WeakMap<File, string>());
  const toast = useToast();

  const addFiles = (files: FileList | File[]) =>
    setPicks((xs) => [...xs, ...Array.from(files).map((f) => ({ file: f, name: f.name, context: "" }))].slice(0, 25));
  const set = (i: number, p: Partial<Pick>) => setPicks((xs) => xs.map((x, j) => (j === i ? { ...x, ...p } : x)));

  async function start() {
    setBusy(true);
    try {
      const items: IntakeItemIn[] = [];
      for (const p of picks) {
        if (p.file) {
          let blob = uploaded.current.get(p.file);
          if (!blob) {
            blob = (await intakeUpload(p.file)).id;
            uploaded.current.set(p.file, blob);
          }
          items.push({ blob_id: blob, name: p.name, context: p.context.trim() || undefined });
        } else if (p.url) items.push({ url: p.url, name: p.name, context: p.context.trim() || undefined });
        else if (p.text) items.push({ text: p.text, name: p.name, context: p.context.trim() || undefined });
      }
      const out = await startIntake({ note: note.trim() || undefined, tier, items });
      setPicks([]); setNote(""); setLink(""); setPaste("");
      onStarted(out.id);
    } catch (err) {
      toast({ kind: "error", title: "Couldn't start the hand-over", detail: (err as Error).message });
    }
    setBusy(false);
  }

  return (
    <section className="vt-card flex flex-col gap-4 p-4 md:p-5" aria-label="Hand over material">
      <div>
        <h3 className="text-sm font-semibold">Hand over your brand material</h3>
        <p className="mt-1 max-w-2xl text-xs leading-5 text-muted">
          Brand books, price sheets, decks, charts, logos, recordings, or a read-only link to live data. Verytas reads each one,
          tells you what it understood, asks about anything it can&apos;t place, and drafts rules, facts, codenames and artwork for
          you to approve. A note on what each file is makes the reading much better.
        </p>
      </div>
      <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); addFiles(e.dataTransfer.files); }}
        className={`flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center text-sm transition-colors ${over ? "border-accent bg-accent/5" : "border-line-strong"}`}>
        <UploadIcon size={18} />
        <span className="text-muted">Drop files here, or</span>
        <label className="vt-btn vt-btn-quiet vt-btn-sm cursor-pointer">
          Choose files
          <input type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
        </label>
        <span className="text-[11px] text-subtle">PDF, Word, PowerPoint, Excel, CSV, JSON, text, images, video, audio. For SAP or a database, export a table or give a read-only link.</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Or a live link" hint="https, read-only, CSV or JSON">
          <div className="flex gap-2">
            <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://example.com/prices.csv" className="vt-input" />
            <button type="button" disabled={!link.trim().startsWith("https://")} className="vt-btn vt-btn-quiet vt-btn-sm"
              onClick={() => { setPicks((xs) => [...xs, { url: link.trim(), name: link.trim().split("/").pop() || "Linked source", context: "" }]); setLink(""); }}>Add</button>
          </div>
        </Field>
        <Field label="Or paste text">
          <div className="flex gap-2">
            <textarea value={paste} onChange={(e) => setPaste(e.target.value)} placeholder="Codenames, a tone guide, a list of approved claims..." className="vt-input min-h-10 text-sm" />
            <button type="button" disabled={!paste.trim()} className="vt-btn vt-btn-quiet vt-btn-sm self-start"
              onClick={() => { setPicks((xs) => [...xs, { text: paste, name: `Pasted text ${xs.filter((x) => x.text).length + 1}`, context: "" }]); setPaste(""); }}>Add</button>
          </div>
        </Field>
      </div>
      {picks.length > 0 && (
        <ul className="flex flex-col divide-y divide-line rounded-xl border border-line">
          {picks.map((p, i) => (
            <li key={`${p.name}-${i}`} className="grid gap-2 px-3 py-2.5 md:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_auto] md:items-center">
              <span className="truncate text-sm font-medium" title={p.name}>{p.name}</span>
              <input value={p.context} onChange={(e) => set(i, { context: e.target.value })} maxLength={4000}
                aria-label={`What is ${p.name}?`} placeholder="What is this? e.g. Q2 board deck, approved to quote" className="vt-input text-xs" />
              <button type="button" onClick={() => setPicks((xs) => xs.filter((_, j) => j !== i))} className="text-xs text-muted hover:text-ink">Remove</button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <Field label="About all of it" hint="optional" className="min-w-56 flex-1">
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={4000} placeholder="Our 2026 brand kit and October pricing" className="vt-input" />
        </Field>
        <Field label="Who may see it">
          <select value={tier} onChange={(e) => setTier(e.target.value)} className="vt-input w-auto pr-8">
            <option value="public">Public</option>
            <option value="internal">Internal</option>
            <option value="confidential">Confidential (read on our server only)</option>
          </select>
        </Field>
        <button type="button" disabled={busy || picks.length === 0} onClick={start} className="vt-btn vt-btn-primary">
          {busy ? "Handing over..." : `Read ${picks.length || ""} item${picks.length === 1 ? "" : "s"}`}
        </button>
      </div>
    </section>
  );
}

function BatchView({ id, onAdded, onClose }: { id: number; onAdded: () => void; onClose: () => void }) {
  const [batch, setBatch] = useState<IntakeBatchDetail | null>(null);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  // Corrections typed into draft rows, kept here so a bulk approval carries them too.
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  // Answers can arrive out of order; one older than what is already shown would put an approved draft back to pending.
  const asked = useRef(0);
  const applied = useRef(0);
  const toast = useToast();

  const load = useCallback(() => {
    const n = ++asked.current;
    return getIntake(id).then((b) => {
      if (n < applied.current) return;
      applied.current = n;
      setBatch(b);
      setLoadError(null);
    }).catch((err: Error) => { if (n > applied.current) setLoadError(err.message); });
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  // Polled while anything is still being read; quiet once every item has an answer, or the hand-over can't be loaded.
  const working = batch ? batch.status === "queued" || batch.status === "running"
    || batch.items.some((i) => i.status === "queued" || i.status === "reading") : !loadError;
  useEffect(() => {
    if (!working) return;
    const t = setInterval(() => void load(), 2000);
    return () => clearInterval(t);
  }, [working, load]);

  const pending = useMemo(() => batch?.drafts.filter((d) => d.status === "pending") ?? [], [batch]);
  const clean = pending.filter((d) => d.issues.length === 0);
  /** What the admin typed into a draft, when it differs from what was read. */
  const correction = (d: IntakeDraft) => (edits[d.id] !== undefined && edits[d.id] !== originalText(d) ? edits[d.id] : null);

  // The bulk endpoint approves drafts as read, so a corrected draft goes through its own approval, which
  // carries the correction. A draft with something to check is left for the admin either way.
  async function bulk(ids: number[]) {
    const byId = new Map((batch?.drafts ?? []).map((d) => [d.id, d] as const));
    const corrected = ids.map((i) => byId.get(i)).filter((d): d is IntakeDraft => Boolean(d) && d!.issues.length === 0 && correction(d!) !== null);
    const plain = ids.filter((i) => !corrected.some((d) => d.id === i));
    setBusy(true);
    let done = 0;
    let skipped = 0;
    try {
      for (const d of corrected) {
        const text = correction(d)!;
        if (!text.trim()) { skipped += 1; continue; }
        try {
          await decideDraft(d.id, "approve", { [fieldOf(d.target)]: text });
          done += 1;
        } catch {
          skipped += 1;
        }
      }
      if (plain.length) {
        const out = await decideDrafts(id, plain);
        done += out.done.length;
        skipped += out.skipped.length;
      }
      toast({ kind: skipped ? "warning" : "success", title: `${done} added to the library`,
        detail: skipped ? `${skipped} left for you to check one by one.` : undefined });
      setChosen(new Set());
    } catch (err) {
      toast({ kind: "error", title: "Couldn't approve", detail: (err as Error).message });
    }
    if (done) onAdded();
    await load();
    setBusy(false);
  }

  if (!batch) {
    return loadError ? (
      <div className="vt-card flex flex-wrap items-center gap-3 p-4 text-sm" role="alert">
        <span className="min-w-0 flex-1 text-[var(--vt-blocker)]">Couldn&apos;t open hand-over #{id}: {loadError}</span>
        <button type="button" onClick={() => void load()} className="vt-btn vt-btn-quiet vt-btn-sm">Try again</button>
        <button type="button" onClick={onClose} className="vt-btn vt-btn-quiet vt-btn-sm">Close</button>
      </div>
    ) : <div className="h-40 animate-pulse rounded-xl bg-sunken" />;
  }
  const groups = (["rule", "fact", "term", "asset"] as const).map((t) => [t, batch.drafts.filter((d) => d.target === t)] as const)
    .filter(([, ds]) => ds.length > 0);
  return (
    <section className="flex flex-col gap-4" aria-label={`Hand-over ${batch.id}`}>
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold">Hand-over #{batch.id}</h3>
        {batch.note && <span className="min-w-0 flex-1 truncate text-sm text-muted">{batch.note}</span>}
        <Badge tone={batch.status === "done" ? "ok" : batch.status === "failed" ? "blocker" : "accent"}>{batch.status === "running" ? "reading..." : batch.status}</Badge>
        <button type="button" onClick={onClose} className="vt-btn vt-btn-quiet vt-btn-sm ml-auto">Close</button>
      </div>
      <ul className="grid gap-3 md:grid-cols-2">
        {batch.items.map((it) => <ItemCard key={it.id} item={it} onChanged={load} />)}
      </ul>
      {groups.length === 0 ? (
        batch.status === "done" && <Empty>Nothing to add from this material yet. Answer any questions above, or add a note on what each file is.</Empty>
      ) : (
        <div className="vt-card flex flex-col gap-4 p-4 md:p-5">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm"><span className="font-semibold">{pending.length}</span> draft{pending.length === 1 ? "" : "s"} to review
              <span className="text-muted"> · nothing is added until you approve it</span></p>
            <div className="ml-auto flex gap-2">
              {chosen.size > 0 && <button type="button" disabled={busy} onClick={() => bulk([...chosen])} className="vt-btn vt-btn-quiet vt-btn-sm">Approve {chosen.size} selected</button>}
              <button type="button" disabled={busy || clean.length === 0} onClick={() => bulk(clean.map((d) => d.id))} className="vt-btn vt-btn-primary vt-btn-sm"
                title="Drafts with something to check are left for you to look at one by one">
                Approve {clean.length} with nothing to check
              </button>
            </div>
          </div>
          {groups.map(([t, ds]) => (
            <div key={t}>
              <p className="mb-1.5 text-xs font-medium text-muted">{TARGET[t]} <span className="text-subtle">({ds.length})</span></p>
              <ul className="flex flex-col divide-y divide-line rounded-xl border border-line">
                {ds.map((d) => (
                  <DraftRow key={d.id} d={d} item={batch.items.find((i) => i.id === d.item_id)} chosen={chosen.has(d.id)}
                    text={edits[d.id] ?? originalText(d)} onText={(t) => setEdits((e) => ({ ...e, [d.id]: t }))}
                    onChoose={(on) => setChosen((s) => { const n = new Set(s); if (on) n.add(d.id); else n.delete(d.id); return n; })}
                    onDone={() => { onAdded(); void load(); }} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ItemCard({ item, onChanged }: { item: IntakeItem; onChanged: () => void }) {
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [rereading, setRereading] = useState(false);
  const toast = useToast();
  const s = STATUS[item.status];
  async function reread() {
    setRereading(true);
    try {
      await refreshIntake(item.id);
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't read the link again", detail: (err as Error).message });
    }
    setRereading(false);
  }
  async function send() {
    setBusy(true);
    try {
      await answerIntake(item.id, answer.trim());
      setAnswer("");
      onChanged();
    } catch (err) {
      toast({ kind: "error", title: "Couldn't send the answer", detail: (err as Error).message });
    }
    setBusy(false);
  }
  return (
    <li className="vt-card flex flex-col gap-2 p-4">
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 truncate text-sm font-medium" title={item.name}>{item.name}</p>
        <Badge tone={s.tone}>{s.label}</Badge>
      </div>
      {item.kind && (
        <p className="text-xs text-muted">
          <span className="capitalize">{item.kind.replaceAll("_", " ")}</span>
          {item.confidence != null && <span className="text-subtle"> · {Math.round(item.confidence * 100)}% sure</span>}
          {item.model && <span className="text-subtle"> · {item.model.startsWith("offline") ? "offline reading" : item.model}</span>}
        </p>
      )}
      {item.purpose && <p className="text-xs leading-5">{item.purpose}</p>}
      {item.error && <p className="text-xs text-[var(--vt-blocker)]">{item.error}</p>}
      {(item.reading.notes?.length ?? 0) > 0 && <p className="text-[11px] text-subtle">{item.reading.notes!.join(" ")}</p>}
      {item.issues.length > 0 && (
        <details className="text-[11px] text-muted"><summary className="cursor-pointer">{item.issues.length} note{item.issues.length === 1 ? "" : "s"} from the reading</summary>
          <ul className="mt-1 list-disc pl-4">{item.issues.slice(0, 12).map((x, i) => <li key={i}>{x.detail}</li>)}</ul></details>
      )}
      {item.status === "needs_context" && (
        <div className="mt-1 flex flex-col gap-2 rounded-lg bg-[var(--vt-warning-bg)] p-3">
          <ul className="flex flex-col gap-1 text-xs text-[var(--vt-warning)]">{item.questions.map((q) => <li key={q}>{q}</li>)}</ul>
          <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={4000} aria-label={`Answer about ${item.name}`}
            placeholder="Your answer, e.g. Active learners in thousands, Jan to Jun 2026, approved to quote" className="vt-input min-h-14 text-xs" />
          <button type="button" disabled={busy || answer.trim().length < 2} onClick={send} className="vt-btn vt-btn-primary vt-btn-sm self-start">
            {busy ? "Sending..." : "Answer and read again"}
          </button>
        </div>
      )}
      {item.source_url && item.status !== "reading" && (
        <button type="button" disabled={rereading} onClick={reread} className="vt-btn vt-btn-quiet vt-btn-sm self-start">
          Read the link again{item.refreshed_at ? ` (last ${new Date(item.refreshed_at).toLocaleString()})` : ""}
        </button>
      )}
    </li>
  );
}

function label(d: IntakeDraft): string {
  const p = d.payload as Record<string, string | number | undefined>;
  return String(p.statement ?? p.title ?? p.term ?? p.name ?? "Draft");
}

function DraftRow({ d, item, chosen, text, onText, onChoose, onDone }: {
  d: IntakeDraft; item?: IntakeItem; chosen: boolean; text: string; onText: (t: string) => void;
  onChoose: (on: boolean) => void; onDone: () => void;
}) {
  const field = fieldOf(d.target);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const p = d.payload as Record<string, string | number | null | undefined>;
  const edited = text !== originalText(d);
  async function decide(action: "approve" | "reject") {
    setBusy(true);
    try {
      await decideDraft(d.id, action, action === "approve" && edited ? { [field]: text } : undefined);
      onDone();
    } catch (err) {
      toast({ kind: "error", title: action === "approve" ? "The library didn't accept it" : "Couldn't reject", detail: (err as Error).message });
    }
    setBusy(false);
  }
  const done = d.status !== "pending";
  return (
    <li className={`grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3 px-3 py-2.5 ${done ? "opacity-60" : ""}`}>
      <input type="checkbox" disabled={done} checked={chosen} onChange={(e) => onChoose(e.target.checked)} aria-label={`Select ${label(d)}`}
        className="mt-1 h-4 w-4 accent-[var(--vt-accent)]" />
      <div className="flex min-w-0 flex-col gap-1.5">
        {d.target === "rule" && <p className="text-sm font-medium">{String(p.title ?? "")} <code className="text-[11px] font-normal text-subtle">{String(p.code ?? "")}</code></p>}
        {done ? <p className="text-sm">{text}</p> : (
          <textarea value={text} onChange={(e) => onText(e.target.value)} rows={d.target === "rule" ? 2 : 1} aria-label="Edit before approving"
            className="w-full resize-y rounded-md bg-transparent px-1 py-0.5 text-sm outline-none hover:bg-sunken focus:bg-sunken" />
        )}
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-subtle">
          {d.target === "fact" && p.value != null && <Badge>{String(p.value)}{p.unit ? ` ${p.unit}` : ""}</Badge>}
          {d.target === "rule" && <Badge tone={p.severity === "must" ? "blocker" : p.severity === "should" ? "warning" : "muted"}>{String(p.severity)}</Badge>}
          <span>from {item?.name ?? d.provenance.source}{d.provenance.cell ? `, ${d.provenance.cell}` : d.provenance.where ? `, ${d.provenance.where}` : ""}</span>
          {d.issues.map((x, i) => <Badge key={i} tone={x.kind === "conflict" ? "blocker" : "warning"}><span title={x.detail}>{ISSUE[x.kind] ?? x.kind}</span></Badge>)}
          {d.status === "approved" && <Badge tone="ok">added</Badge>}
          {d.status === "rejected" && <Badge>rejected</Badge>}
        </div>
        {d.provenance.quote && <p className="line-clamp-2 border-l-2 border-line pl-2 text-[11px] text-muted">&ldquo;{d.provenance.quote}&rdquo;</p>}
        {d.issues.length > 0 && !done && <p className="text-[11px] text-[var(--vt-warning)]">{d.issues.map((x) => x.detail).join(" · ")}</p>}
        {!done && (
          <div className="flex gap-2">
            <button type="button" disabled={busy || !text.trim()} onClick={() => decide("approve")} className="vt-btn vt-btn-primary vt-btn-xs">{edited ? "Approve edited" : "Approve"}</button>
            <button type="button" disabled={busy} onClick={() => decide("reject")} className="vt-btn vt-btn-quiet vt-btn-xs">Reject</button>
          </div>
        )}
      </div>
    </li>
  );
}

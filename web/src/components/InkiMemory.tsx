"use client";

import { useCallback, useEffect, useState } from "react";
import { api, relativeTime } from "@/lib/review-client";
import { CloseIcon } from "./Icons";
import { INKI, InkiIcon } from "./Inki";
import { useToast } from "./Toaster";
import { shownError } from "@/lib/errors";

type Memory = { id: string; text: string; created_at: string | null; updated_at: string | null };

/**
 * What Inki has kept about this person from Ask Inki: their own words about how they work, never anything
 * from a shared conversation. Each can be removed, or all of it at once; nothing here is shown to anyone else.
 */
export function InkiMemory() {
  const toast = useToast();
  const [rows, setRows] = useState<Memory[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);

  const load = useCallback(() => {
    api<Memory[]>("me/memories").then((r) => { setRows(r); setError(null); }).catch((e: unknown) => setError(shownError(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const forget = async (id?: string) => {
    try {
      await api(id ? `me/memories/${id}` : "me/memories", { method: "DELETE" });
      setRows((r) => (id ? r?.filter((m) => m.id !== id) ?? null : []));
      setConfirm(false);
      toast({ kind: "success", title: id ? "Forgotten" : `${INKI} forgot everything it kept about you` });
    } catch (e) {
      toast({ kind: "error", title: "Couldn't forget that", detail: shownError(e) });
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <InkiIcon size={32} className="shrink-0" />
        <p className="text-[13px] leading-5 text-muted">
          What you tell {INKI} in Ask Inki about how you work (your channels, your role, how you like answers) is kept
          here so it can help you better next time. Only you see this list. Nothing is kept from conversations with
          other people, and confidential terms are never kept.
        </p>
      </div>
      {error && <p role="alert" className="rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-2 text-[13px] text-[var(--vt-blocker)]">{error}</p>}
      {rows === null && !error ? (
        <div aria-busy="true" className="flex flex-col gap-2">{[0, 1].map((i) => <div key={i} className="h-10 animate-pulse rounded-lg bg-sunken" />)}</div>
      ) : rows && rows.length === 0 ? (
        <p className="rounded-lg bg-sunken px-3 py-3 text-[13px] text-muted">{INKI} hasn&apos;t kept anything about you yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {rows?.map((m) => (
            <li key={m.id} className="group flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2">
              <span className="min-w-0 flex-1 text-[13px]">{m.text}</span>
              <span className="shrink-0 text-[11px] text-subtle">{relativeTime(m.updated_at ?? m.created_at)}</span>
              <button type="button" onClick={() => void forget(m.id)} aria-label={`Forget: ${m.text}`} title="Forget this"
                className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-subtle transition hover:bg-sunken hover:text-ink">
                <CloseIcon size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {rows && rows.length > 0 && (confirm ? (
        <div className="vt-pop flex items-center gap-2 self-end rounded-xl bg-[var(--vt-blocker-bg)] py-1 pl-3 pr-1 text-xs">
          <span className="font-medium text-[var(--vt-blocker)]">Forget all {rows.length}?</span>
          <button type="button" onClick={() => void forget()} className="vt-btn vt-btn-xs text-[var(--vt-blocker)]">Forget all</button>
          <button type="button" onClick={() => setConfirm(false)} className="vt-btn vt-btn-quiet vt-btn-xs">Keep</button>
        </div>
      ) : (
        <button type="button" onClick={() => setConfirm(true)} className="vt-btn vt-btn-quiet self-end text-xs">Forget everything</button>
      ))}
    </div>
  );
}

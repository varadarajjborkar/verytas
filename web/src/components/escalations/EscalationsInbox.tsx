"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, isOffline, listEscalations, PRIORITY, relativeTime, resolveEscalation } from "@/lib/review-client";
import { canDecide } from "@/lib/roles";
import type { EscalationRequest, FactCitation, RuleCitation } from "@/lib/types";
import { CheckIcon, ChevronIcon } from "../Icons";
import { SummarizeButton } from "../assist/SummarizeButton";
import { TalkCard } from "../conversations/TalkCard";
import { PriorityPill } from "../review/Checklist";
import { REASONS } from "../review/DecisionControls";
import { useToast } from "../Toaster";
import { tabKeys } from "../ui";
import { useViewer } from "../Viewer";
import { channelName } from "@/lib/channels";
import { useOnRefresh } from "@/lib/refresh";
import { onLive } from "@/lib/live";
import { shownError } from "@/lib/errors";

const FLAG_TONE: Record<string, string> = {
  pressure: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
  link: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
  unlisted_contact: "bg-[var(--vt-warning-bg)] text-[var(--vt-warning)]",
  public_contact: "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]",
};
const REASON_LABEL: Record<string, string> = Object.fromEntries(REASONS.map((r) => [r.code, r.label]));

/**
 * Creators asking a person to look at a finding. Each row puts the three things a
 * decision needs side by side: the passage with the issue, the library record the
 * finding cites (readable in full without leaving the row), and what the creator
 * said. Deciding records an ordinary decision on the finding, so approval gating
 * and guideline health learn from it.
 */
export function EscalationsInbox() {
  const { me } = useViewer();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = params.get("tab") === "resolved" ? "resolved" : "open";
  const focus = Number(params.get("id")) || null;
  const [rows, setRows] = useState<EscalationRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creator, setCreator] = useState("all");
  const [level, setLevel] = useState("all");

  // Only the newest request may fill the list, so a slow "Waiting" reply can't land on the "Decided" tab.
  const seq = useRef(0);
  const load = useCallback(() => {
    const ticket = ++seq.current;
    listEscalations(tab).then((r) => {
      if (ticket !== seq.current) return;
      setRows(r);
      setError(null);
    }).catch((err) => {
      if (ticket === seq.current) setError(isOffline(err) ? "Escalations need the Verytas API." : shownError(err));
    });
  }, [tab]);
  useEffect(() => { load(); }, [load]);
  useOnRefresh(load);
  // Raised, answered or withdrawn by anyone: the list follows at once rather than on the next visit.
  useEffect(() => onLive((e) => { if (e.type === "escalations") load(); }), [load]);
  useEffect(() => {
    if (!focus || !rows) return;
    document.getElementById(`esc-${focus}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focus, rows]);

  const creators = useMemo(() => [...new Map((rows ?? []).flatMap((r) => (r.raised_by ? [[r.raised_by.id, r.raised_by]] : []))).values()]
    .sort((a, b) => a.name.localeCompare(b.name)), [rows]);
  const shown = (rows ?? []).filter((r) => (creator === "all" || String(r.raised_by?.id) === creator)
    && (level === "all" || r.finding.level === level));
  const approver = me?.role === "approver" || me?.role === "brand_admin";
  // Auditors read the inbox; deciding is for reviewers, approvers and brand admins.
  const decider = canDecide(me?.role);
  const setTab = (t: string) => router.replace(t === "open" ? pathname : `${pathname}?tab=${t}`, { scroll: false });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label="Escalations" className="inline-flex rounded-lg bg-sunken p-0.5 text-[13px] font-medium"
          onKeyDown={tabKeys(["open", "resolved"] as const, tab, setTab, "esc-tab")}>
          {(["open", "resolved"] as const).map((t) => (
            <button key={t} id={`esc-tab-${t}`} type="button" role="tab" aria-selected={tab === t} aria-controls="esc-panel"
              tabIndex={tab === t ? 0 : -1} onClick={() => setTab(t)}
              className={`rounded-md px-3 py-2 transition ${tab === t ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
              {t === "open" ? "Waiting for you" : "Decided"}
              {t === tab && rows ? <span className="ml-1.5 tabular-nums text-subtle">{rows.length}</span> : null}
            </button>
          ))}
        </div>
        <select value={creator} onChange={(e) => setCreator(e.target.value)} aria-label="Creator" className="vt-input vt-select h-9 w-auto py-0 text-[13px]">
          <option value="all">Every creator</option>
          {creators.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Severity" className="vt-input vt-select h-9 w-auto py-0 text-[13px]">
          <option value="all">Any severity</option>
          <option value="blocker">{PRIORITY.blocker.label}</option>
          <option value="warning">{PRIORITY.warning.label}</option>
        </select>
      </div>

      {error ? <p className="vt-card p-6 text-sm text-muted">{error}</p>
        : rows === null ? <div className="flex flex-col gap-3">{[0, 1].map((i) => <div key={i} className="h-44 animate-pulse rounded-[14px] bg-sunken" />)}</div>
          : shown.length === 0 ? (
            <div className="vt-card px-6 py-10 text-center">
              <p className="text-sm font-medium">{tab === "open" ? "Nothing is waiting for you" : "No decisions yet"}</p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted">
                When a creator thinks a finding is wrong, they can ask a person to look. Their request lands here with the
                passage, the rule or fact behind the finding, and what they said.
              </p>
            </div>
          ) : (
            // One table on a wide screen; below that each request is its own card, so two stacked requests
            // never read as one long one.
            <section id="esc-panel" role="tabpanel" aria-labelledby={`esc-tab-${tab}`}
              className="xl:overflow-hidden xl:rounded-[14px] xl:border xl:border-line xl:bg-surface xl:shadow-[var(--vt-shadow)]">
              <div className="hidden grid-cols-[minmax(0,1.25fr)_minmax(0,1.1fr)_minmax(0,1fr)_15rem] gap-5 border-b border-line bg-sunken/50 px-5 py-2.5 text-[11px] font-medium uppercase tracking-wide text-subtle xl:grid">
                <span>The content</span><span>What the record says</span><span>What the creator said</span><span>Decision</span>
              </div>
              <ul className="flex flex-col gap-4 xl:gap-0">
                {shown.map((r) => <Row key={r.id} r={r} focused={r.id === focus} approver={approver} decider={decider} onDone={load} />)}
              </ul>
            </section>
          )}

      <TalkCard side="manager" />
    </div>
  );
}

function Row({ r, focused, approver, decider, onDone }: {
  r: EscalationRequest; focused: boolean; approver: boolean; decider: boolean; onDone: () => void;
}) {
  return (
    <li id={`esc-${r.id}`} className={`grid gap-4 rounded-[14px] border border-line px-4 py-5 shadow-[var(--vt-shadow)] transition-colors md:grid-cols-2 md:gap-5 md:px-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1.1fr)_minmax(0,1fr)_15rem] xl:rounded-none xl:border-0 xl:border-b xl:shadow-none xl:last:border-b-0 ${
      focused ? "bg-[color-mix(in_oklab,var(--vt-accent)_5%,var(--vt-surface))]" : "bg-surface"}`}>
      <Cell label="The content">
        <div className="flex items-start justify-between gap-2">
          <Link href={`/review?id=${r.content.id}`} className="block min-w-0 text-sm font-semibold leading-5 hover:text-accent [overflow-wrap:anywhere]">{r.content.title}</Link>
          <SummarizeButton kind="escalation" id={r.id} title={r.content.title} className="vt-btn vt-btn-quiet vt-btn-xs shrink-0" />
        </div>
        <p className="mt-0.5 truncate text-[11px] text-subtle">
          {r.content.author?.name ?? "Creator"} · {channelName(r.content.channel)}
          {r.version ? ` · v${r.version.version_no}` : ""}
        </p>
        <div className="mt-3 flex items-start gap-2">
          <PriorityPill level={r.finding.level} />
          <p className="min-w-0 text-[13px] font-medium leading-5">{r.finding.title}</p>
        </div>
        <blockquote className="mt-2.5 rounded-lg bg-sunken px-3 py-2.5 text-[13px] leading-6 text-muted">
          {r.excerpt.clipped_start && "..."}{r.excerpt.before}
          {r.excerpt.quote && <mark data-level={r.finding.level} className="text-ink">{r.excerpt.quote}</mark>}
          {r.excerpt.after}{r.excerpt.clipped_end && "..."}
        </blockquote>
        <p className="mt-2 text-xs leading-5 text-muted">{r.finding.explanation}</p>
        <p className="mt-1 text-[11px] text-subtle">
          {r.finding.model ? `Judged by ${r.finding.model}` : "Rule-based check"} · {Math.round(r.finding.confidence * 100)}% sure
        </p>
      </Cell>

      <Cell label="What the record says">
        {r.citations.length === 0 ? (
          <p className="text-xs text-muted">No library record: a built-in check ({r.finding.checker}) raised it.</p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {r.citations.map((c) => (c.kind === "rule" ? <RuleCard key={`r${c.id}`} c={c} /> : <FactCard key={`f${c.id}`} c={c} />))}
          </div>
        )}
      </Cell>

      <Cell label="What the creator said">
        <blockquote className="border-l border-line-strong pl-3 text-[13px] leading-6">&ldquo;{r.message}&rdquo;</blockquote>
        <p className="mt-2 text-[11px] text-subtle">
          {r.raised_by?.name ?? "Creator"} · {relativeTime(r.created_at)}
          {r.raised_before > 0 ? ` · ${r.raised_before} earlier request${r.raised_before === 1 ? "" : "s"}` : " · first request"}
        </p>
        {r.guard.flagged.length > 0 && (
          <ul className="mt-2.5 flex flex-wrap gap-1.5" aria-label="Screening notes">
            {r.guard.flagged.map((g, i) => (
              <li key={i} className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${FLAG_TONE[g.code] ?? "bg-sunken text-muted"}`}
                title={g.quote}>{g.label.replace(/^(names|uses|contains) /, (m) => m[0].toUpperCase() + m.slice(1))}</li>
            ))}
          </ul>
        )}
      </Cell>

      <Cell label="Decision">
        {r.status !== "open" ? <Outcome r={r} />
          : decider ? <Decide r={r} approver={approver} onDone={onDone} />
            : <p className="text-xs text-muted">Waiting for a reviewer or approver.</p>}
      </Cell>
    </li>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    // Stacked on a phone, each part gets a rule above it so four sections don't run together.
    <div className="min-w-0 border-t border-dashed border-line pt-4 first:border-0 first:pt-0 md:border-0 md:pt-0">
      <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-subtle xl:hidden">{label}</p>
      {children}
    </div>
  );
}

function RuleCard({ c }: { c: RuleCitation }) {
  const [open, setOpen] = useState(false);
  const severity = { must: "Must", should: "Should", may: "May" }[c.severity];
  return (
    // A quoted source, marked by a rule on its left edge rather than boxed: it already sits in a card.
    <div className="border-l-2 border-line-strong">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-start gap-2 py-1 pl-3 text-left">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px] text-subtle">
            <span className="whitespace-nowrap rounded bg-sunken px-1.5 py-px font-mono text-[11px] text-muted">{c.code}</span>
            <span>Rule · {severity}{c.event_id ? " · from an event" : c.system ? " · built in" : ""}</span>
          </p>
          <p className="mt-1 text-[13px] font-medium leading-5">{c.title}</p>
          <p className={`mt-1 text-xs leading-5 text-muted ${open ? "" : "line-clamp-2"}`}>{c.text}</p>
        </div>
        <ChevronIcon size={15} className={`mt-0.5 shrink-0 text-subtle transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="vt-pop flex flex-col gap-2 pb-1 pl-3 pt-2.5 text-xs">
          {terms(c.pattern) && <p><span className="text-muted">Matches: </span>{terms(c.pattern)}</p>}
          {c.good_examples.length > 0 && <p><span className="font-medium text-[var(--vt-ok)]">On brand: </span>{c.good_examples.map((x) => `“${x}”`).join(", ")}</p>}
          {c.bad_examples.length > 0 && <p><span className="font-medium text-[var(--vt-blocker)]">Off brand: </span>{c.bad_examples.map((x) => `“${x}”`).join(", ")}</p>}
          <p className="text-subtle">
            {c.source_ref ?? "No source recorded"} · version {c.version}
            {c.latest_version && c.latest_version > c.version ? ` (now v${c.latest_version}: the rule changed since)` : ""}
            {c.status !== "active" ? ` · ${c.status}` : ""}
          </p>
          <Link href={`/library?q=${encodeURIComponent(c.code)}`} className="self-start font-medium text-accent hover:underline">Open in the library</Link>
        </div>
      )}
    </div>
  );
}

function terms(pattern: Record<string, unknown>): string | null {
  if (Array.isArray(pattern.terms)) return (pattern.terms as string[]).join(", ");
  if (pattern.map && typeof pattern.map === "object") return Object.entries(pattern.map as Record<string, string>).map(([w, r]) => `${w} → ${r}`).join(", ");
  return null;
}

function FactCard({ c }: { c: FactCitation }) {
  return (
    <div className="border-l-2 border-[var(--vt-ok)] py-1 pl-3">
      <p className="flex items-center gap-1.5 text-[11px] text-subtle">
        <span>Approved fact</span>
        <span className={`rounded px-1.5 py-px text-[11px] font-medium ${c.valid_today ? "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]" : "bg-sunken text-muted"}`}>
          {c.valid_today ? "Valid today" : "Not valid today"}
        </span>
      </p>
      <p className="mt-1 text-[13px] font-medium leading-5">{c.statement}</p>
      <p className="mt-1 text-[11px] text-subtle">{c.source_ref} · {c.valid_from} to {c.valid_to ?? "open"}</p>
    </div>
  );
}

function Decide({ r, approver, onDone }: { r: EscalationRequest; approver: boolean; onDone: () => void }) {
  const [clearing, setClearing] = useState(false);
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const blocked = r.finding.level === "blocker" && !approver;
  const run = async (outcome: "upheld" | "cleared") => {
    setBusy(true);
    try {
      await resolveEscalation(r.id, outcome, outcome === "cleared" ? code : null, note.trim());
      toast({ kind: "success", title: outcome === "cleared" ? "Finding cleared" : "Finding stands", detail: `${r.raised_by?.name ?? "The creator"} will see your note.` });
      onDone();
    } catch (err) {
      const d = err instanceof ApiError ? err.detail as { message?: string } : null;
      toast({ kind: "error", title: "Couldn't record it", detail: d?.message ?? shownError(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex flex-col gap-2">
      <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} aria-label="Note for the creator"
        placeholder="Note for the creator" className="vt-input min-h-16 text-xs" />
      {clearing && (
        <select value={code} onChange={(e) => setCode(e.target.value)} aria-label="Why clear it" className="vt-input vt-select py-1.5 text-xs">
          <option value="" disabled>Why clear it?</option>
          {REASONS.map((x) => <option key={x.code} value={x.code}>{x.label}</option>)}
        </select>
      )}
      <div className="grid grid-cols-2 gap-1.5">
        <button type="button" disabled={busy} onClick={() => run("upheld")} className="vt-btn vt-btn-quiet vt-btn-sm"
          title="The finding is right: the creator fixes it">Uphold</button>
        {clearing ? (
          <button type="button" disabled={busy || !code} onClick={() => run("cleared")} className="vt-btn vt-btn-primary vt-btn-sm">Clear it</button>
        ) : (
          <button type="button" disabled={busy || blocked} onClick={() => setClearing(true)} className="vt-btn vt-btn-quiet vt-btn-sm"
            title={blocked ? "Only approvers clear a must-fix finding" : "The finding is wrong here: dismiss it, with a reason"}>Clear</button>
        )}
      </div>
      {blocked && <p className="text-[11px] text-subtle">Must-fix findings are cleared by an approver.</p>}
    </div>
  );
}

function Outcome({ r }: { r: EscalationRequest }) {
  const cleared = r.status === "cleared";
  return (
    <div className="text-xs">
      <p className={`flex items-center gap-1.5 font-semibold ${cleared ? "text-[var(--vt-ok)]" : r.status === "withdrawn" ? "text-subtle" : "text-[var(--vt-blocker)]"}`}>
        {cleared && <CheckIcon size={13} />}{{ cleared: "Cleared", upheld: "Finding stands", withdrawn: "Withdrawn", open: "" }[r.status]}
      </p>
      {r.resolution?.by && <p className="mt-0.5 text-subtle">{r.resolution.by.name} · {relativeTime(r.resolved_at)}</p>}
      {r.resolution?.code && <p className="mt-1 text-muted">{REASON_LABEL[r.resolution.code] ?? r.resolution.code}</p>}
      {r.resolution?.note && <p className="mt-1 text-muted">&ldquo;{r.resolution.note}&rdquo;</p>}
    </div>
  );
}

"use client";

// The brand team's dashboard widgets. Each one reads the same shared data
// (DashData) and renders inside a Panel; the dashboard decides which ones show,
// in what order and at what width.

import Link from "next/link";
import type { ReactNode } from "react";
import { priority, sinceOf } from "@/lib/queue";
import { relativeTime } from "@/lib/review-client";
import type { BrandEvent, ContentRow, CreatorRow, EscalationRequest, Overview, Person, Recurring, RuleHealth } from "@/lib/types";
import { byWaiting, CreatorTable } from "../creators/CreatorTable";
import { ArrowRightIcon, GaugeIcon, InboxIcon, OctagonIcon, ReviewIcon } from "../Icons";
import { StageDots } from "../Journey";
import { PipelineFlow } from "../home/PipelineFlow";
import { today } from "../library/parts";
import { PriorityPill } from "../review/Checklist";
import { HBars, Meter, Panel, RuleCode, Stat, TrendBars } from "../ui";

export type DashData = {
  overview: Overview;
  recurring: Recurring[];
  health: RuleHealth[];
  rows: ContentRow[] | null;
  people: Map<number, Person>;
  escalations: EscalationRequest[] | null;
  events: BrandEvent[] | null;
  creators: CreatorRow[] | null;
  demo: boolean;
};

export type Size = "half" | "full";
export type WidgetDef = {
  title: string;
  /** One line for the "add a widget" tray. */
  blurb: string;
  size: Size;
  link?: { href: string; label: string };
  /** Drawn without a panel: its own tiles are the containers (no card inside a card). */
  bare?: boolean;
  render: (d: DashData) => ReactNode;
};

// The API starts advising a rewrite at this ambiguity (api/insights.py).
export const UNCLEAR = 0.5;
const LEVEL_PALETTE = ["#e0604f", "#e0a04a", "#8aa6c4"];
const pct = (v: number | null | undefined) => (v == null ? "n/a" : `${Math.round(v * 100)}%`);
const nameOf = (d: DashData, id: number) => d.people.get(id)?.name ?? "Creator";

function Skeleton({ rows = 3 }: { rows?: number }) {
  return <ul className="flex flex-col gap-2">{Array.from({ length: rows }, (_, i) => <li key={i} className="h-10 animate-pulse rounded-lg bg-sunken" />)}</ul>;
}
function NeedsApi() {
  return <p className="text-sm text-muted">This needs the Verytas API. The other widgets show sample data.</p>;
}

export const WIDGETS: Record<string, WidgetDef> = {
  knows: {
    title: "Need to know", blurb: "What is waiting, escalated and blocked right now.", size: "full", bare: true,
    render: (d) => {
      const waiting = (d.rows ?? []).filter((r) => r.status === "in_review");
      const oldest = [...waiting].sort((a, b) => sinceOf(a).localeCompare(sinceOf(b)))[0];
      const blockers = waiting.reduce((n, r) => n + (r.latest_review?.blockers ?? 0), 0);
      const unclear = d.health.filter((h) => h.ambiguity != null && h.ambiguity >= UNCLEAR).length;
      const asks = d.escalations?.length ?? null;
      const tiles = [
        { label: "Waiting for a decision", value: d.rows ? waiting.length : d.overview.content.in_review ?? 0, Icon: ReviewIcon,
          href: "/review", hint: oldest ? `Oldest sent ${relativeTime(sinceOf(oldest))}` : "Queue is clear", tone: "text-accent" },
        { label: "Creators asking for a person", value: asks ?? "n/a", Icon: InboxIcon, href: "/escalations",
          hint: asks ? "Decide with the record beside it" : "None open", tone: asks ? "text-accent" : "text-subtle" },
        { label: "Must-fix issues in the queue", value: d.rows ? blockers : "n/a", Icon: OctagonIcon, href: "/review?signal=mustfix",
          hint: blockers ? "Approving needs a noted override" : "None open", tone: blockers ? "text-[var(--vt-blocker)]" : "text-subtle" },
        { label: "Rules that look unclear", value: unclear, Icon: GaugeIcon, href: "/guidelines",
          hint: d.overview.reviews.failed ? `${d.overview.reviews.failed} checks failed` : unclear ? "Reviewers keep overriding them" : "None stand out",
          tone: unclear ? "text-[var(--vt-warning)]" : "text-subtle" },
      ];
      return (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {tiles.map((t) => (
            <Link key={t.label} href={t.href} className="vt-card vt-lift group p-4">
              <span className="flex items-center gap-1.5 text-xs font-medium text-muted"><t.Icon size={14} className={t.tone} />{t.label}</span>
              <span className="mt-1.5 block text-[1.6rem] font-semibold leading-none tracking-tight tabular-nums">{t.value}</span>
              <span className="mt-2 line-clamp-2 text-xs leading-5 text-subtle">{t.hint}</span>
            </Link>
          ))}
        </div>
      );
    },
  },
  queue: {
    title: "Needs your decision", blurb: "The waiting pieces, most urgent first.", size: "half",
    link: { href: "/review", label: "Open queue" },
    render: (d) => {
      if (d.demo) return <NeedsApi />;
      if (!d.rows) return <Skeleton />;
      const waiting = d.rows.filter((r) => r.status === "in_review").sort((a, b) => priority(b) - priority(a)).slice(0, 6);
      if (!waiting.length) return <p className="text-sm text-muted">Nothing is waiting. Pieces appear here when creators send them.</p>;
      return (
        <ul className="-mx-2 flex flex-col">
          {waiting.map((r) => (
            <li key={r.id}>
              <Link href={`/review?id=${r.id}`} className="group flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-sunken">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{r.title}</p>
                  <p className="truncate text-[11px] text-subtle">{nameOf(d, r.created_by)} · sent {relativeTime(sinceOf(r))}</p>
                </div>
                {r.latest_review?.blockers ? (
                  <span className="shrink-0 rounded-full bg-[var(--vt-blocker-bg)] px-1.5 text-[11px] font-semibold tabular-nums text-[var(--vt-blocker)]">
                    {r.latest_review.blockers} must-fix
                  </span>
                ) : r.latest_review?.overall != null ? <span className="shrink-0 text-xs tabular-nums text-muted">{Math.round(r.latest_review.overall * 100)}%</span> : null}
                <ArrowRightIcon size={14} className="shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-ink" />
              </Link>
            </li>
          ))}
        </ul>
      );
    },
  },
  flow: {
    title: "How work is flowing", blurb: "The approval pipeline, with the loop back to creators.", size: "half",
    render: (d) => <PipelineFlow counts={d.overview.content} />,
  },
  creators: {
    title: "Your creators", blurb: "What each creator has waiting, and how far their recent pieces drift.", size: "half",
    link: { href: "/creators", label: "All creators" },
    render: (d) => {
      if (d.demo) return <NeedsApi />;
      if (!d.creators) return <Skeleton rows={4} />;
      return <CreatorTable rows={byWaiting(d.creators).slice(0, 7)} compact />;
    },
  },
  escalations: {
    title: "Asked for a person", blurb: "Open escalations from creators, oldest first.", size: "half",
    link: { href: "/escalations", label: "Open inbox" },
    render: (d) => {
      if (d.demo) return <NeedsApi />;
      if (!d.escalations) return <Skeleton />;
      if (!d.escalations.length) return <p className="text-sm text-muted">No creator is waiting on a person.</p>;
      return (
        <ul className="-mx-2 flex flex-col">
          {d.escalations.slice(0, 5).map((e) => (
            <li key={e.id}>
              <Link href={`/escalations?id=${e.id}`} className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-sunken">
                <PriorityPill level={e.finding.level} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{e.finding.title}</p>
                  <p className="truncate text-[11px] text-subtle">{e.raised_by?.name ?? "Creator"} on {e.content.title} · {relativeTime(e.created_at)}</p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      );
    },
  },
  events: {
    title: "Brand events", blurb: "What is running and coming up, and what it re-checked.", size: "half",
    link: { href: "/library?tab=events", label: "Manage" },
    render: (d) => {
      if (d.demo) return <NeedsApi />;
      if (!d.events) return <Skeleton />;
      const on = today();
      const list = d.events.filter((e) => e.status === "active" && (!e.ends_on || e.ends_on >= on))
        .sort((a, b) => Number(b.live) - Number(a.live) || a.starts_on.localeCompare(b.starts_on));
      if (!list.length) return <p className="text-sm text-muted">No events running or scheduled. Add one in the library.</p>;
      return (
        <ul className="flex flex-col gap-3">
          {list.map((e) => (
            <li key={e.id} className="flex items-start gap-3">
              <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${e.live ? "bg-[var(--vt-ok)]" : "bg-accent"}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{e.name}{e.blackout ? <span className="ml-1.5 text-[11px] font-medium text-[var(--vt-warning)]">blackout</span> : null}</p>
                <p className="truncate text-[11px] text-subtle">
                  {e.live ? "Running" : `Starts ${e.starts_on}`}{e.ends_on ? ` until ${e.ends_on}` : ""} · {e.pieces} piece{e.pieces === 1 ? "" : "s"} for it
                </p>
              </div>
            </li>
          ))}
        </ul>
      );
    },
  },
  recent: {
    title: "Recently active", blurb: "The latest pieces, with where each one is.", size: "full",
    link: { href: "/review?queue=all", label: "All pieces" },
    render: (d) => {
      if (d.demo) return <NeedsApi />;
      if (!d.rows) return <Skeleton rows={4} />;
      return (
        <ul className="grid gap-x-6 gap-y-1 md:grid-cols-2">
          {d.rows.slice(0, 8).map((r) => (
            <li key={r.id}>
              <Link href={`/review?queue=all&id=${r.id}`} className="flex items-center gap-3 rounded-lg py-1.5 text-sm hover:text-accent">
                <StageDots status={r.status} checked={r.latest_review?.status === "done"} />
                <span className="min-w-0 flex-1 truncate">{r.title}</span>
                <span className="shrink-0 text-[11px] text-subtle">{relativeTime(r.updated_at ?? r.created_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      );
    },
  },
  stats: {
    title: "Totals", blurb: "Reviews, findings, blockers caught, fixes accepted, published.", size: "full",
    render: (d) => {
      const o = d.overview;
      const inFlight = (o.content.in_review ?? 0) + (o.content.changes_requested ?? 0);
      return (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat label="Reviews" value={o.reviews.total.toLocaleString()} hint={o.reviews.failed ? `${o.reviews.failed} failed` : undefined} />
          <Stat label="Findings" value={o.findings.total.toLocaleString()} />
          <Stat label="Blockers caught" value={(o.findings.by_level.blocker ?? 0).toLocaleString()} />
          <Stat label="Fixes accepted" value={pct(o.decisions.acceptance_rate)} />
          <Stat label="Published" value={(o.content.published ?? 0).toLocaleString()} hint={inFlight ? `${inFlight} in review` : undefined} />
        </div>
      );
    },
  },
  trend: {
    title: "Findings, last 14 days", blurb: "Blockers, warnings and advisories per day.", size: "full",
    render: (d) => (
      <div className="h-48">
        <TrendBars data={d.overview.trend.slice(-14).map((t) => ({ label: t.day.slice(5), values: [t.blocker, t.warning, t.advisory] }))}
          series={[{ name: "Blockers", colour: LEVEL_PALETTE[0] }, { name: "Warnings", colour: LEVEL_PALETTE[1] }, { name: "Advisories", colour: LEVEL_PALETTE[2] }]} />
      </div>
    ),
  },
  sources: {
    title: "Where issues come from", blurb: "Findings by category.", size: "half",
    render: (d) => <HBars data={Object.entries(d.overview.findings.by_category).sort((a, b) => b[1] - a[1]).slice(0, 6)
      .map(([label, value]) => ({ label, value }))} />,
  },
  rules: {
    title: "Busiest rules", blurb: "The rules that fire most.", size: "half",
    link: { href: "/library", label: "Library" },
    render: (d) => (
      <ul className="divide-y divide-line">
        {d.overview.top_rules.slice(0, 6).map((r) => (
          <li key={r.rule_id} className="flex items-center gap-3 py-2.5 text-sm first:pt-0 last:pb-0">
            <RuleCode code={r.code} className="w-40" />
            <span className="min-w-0 flex-1 truncate" title={r.title}>{r.title}</span>
            <span className="tabular-nums">{r.findings}</span>
          </li>
        ))}
      </ul>
    ),
  },
  recurring: {
    title: "Recurring phrases", blurb: "Wording that keeps getting flagged.", size: "half",
    render: (d) => (
      <ul className="divide-y divide-line">
        {d.recurring.slice(0, 5).map((r) => (
          <li key={`${r.rule}-${r.phrase}`} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">&ldquo;{r.phrase}&rdquo;</p>
              <p className="truncate text-xs text-subtle">{r.title}</p>
            </div>
            <p className="shrink-0 text-sm tabular-nums" title={`${r.count} times across ${r.reviews} reviews`}>{r.count}</p>
          </li>
        ))}
      </ul>
    ),
  },
  unclear: {
    title: "Rules that look unclear", blurb: "Rules reviewers override or disagree on.", size: "half",
    link: { href: "/guidelines", label: "View all" },
    render: (d) => {
      const list = d.health.filter((h) => h.ambiguity != null && h.ambiguity >= UNCLEAR).slice(0, 4);
      if (!list.length) return <p className="text-sm text-muted">Nothing stands out yet. This fills in as reviewers decide on findings.</p>;
      return (
        <ul className="flex flex-col gap-4">
          {list.map((h) => (
            <li key={h.rule_id}>
              <div className="mb-1.5 flex items-baseline justify-between gap-3">
                <p className="truncate text-sm font-medium">{h.title}</p>
                <code className="shrink-0 text-xs text-subtle">{h.code}</code>
              </div>
              <Meter value={h.ambiguity ?? 0} label={`Ambiguity of ${h.code}`} tone="danger" />
            </li>
          ))}
        </ul>
      );
    },
  },
};

export const DEFAULT_LAYOUT: { id: string; size: Size }[] = [
  // Halves alternate between the two columns, so neighbours are paired by height: decisions beside
  // creators, the flow beside the asks.
  { id: "knows", size: "full" }, { id: "queue", size: "half" }, { id: "creators", size: "half" },
  { id: "flow", size: "half" }, { id: "escalations", size: "half" }, { id: "trend", size: "full" },
  { id: "sources", size: "half" }, { id: "rules", size: "half" },
];

/** A widget in its panel, used both in place and while editing. */
export function WidgetPanel({ id, d, editing = false }: { id: string; d: DashData; editing?: boolean }) {
  const w = WIDGETS[id];
  if (w.bare) return <section aria-label={w.title}>{w.render(d)}</section>;
  return (
    <Panel title={w.title} className="h-full"
      // While editing, the corner controls sit where the link would be; the link is no use then anyway.
      aside={w.link && !editing ? <Link href={w.link.href} className="text-xs font-medium text-accent hover:underline">{w.link.label}</Link> : undefined}>
      {w.render(d)}
    </Panel>
  );
}


"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ApiError, listAssets, listContacts, listEvents, listFacts, listRules, listTerms } from "@/lib/review-client";
import { canEditLibrary } from "@/lib/roles";
import type { BrandAsset, BrandEvent, Fact, PublicContact, Rule, Term } from "@/lib/types";
import { tabKeys } from "../ui";
import { useViewer } from "../Viewer";
import { AssetsTab } from "./AssetsTab";
import { ContactsTab } from "./ContactsTab";
import { EventsTab } from "./EventsTab";
import { FactsTab } from "./FactsTab";
import { ImportTab } from "./ImportTab";
import { ListSkeleton, ReadOnlyNote, today } from "./parts";
import { RulesTab } from "./RulesTab";
import { TermsTab } from "./TermsTab";

type Tab = "rules" | "facts" | "events" | "contacts" | "terms" | "assets" | "import";
const TABS: Tab[] = ["rules", "facts", "events", "contacts", "terms", "assets", "import"];
type Data = { rules: Rule[]; facts: Fact[]; terms: Term[] | null; assets: BrandAsset[]; events: BrandEvent[]; contacts: PublicContact[] };

/**
 * Everything a review checks against, in one place: the rules, the facts posts
 * may cite, the confidential terms that must not leak, and the official
 * artwork. The tabs double as a summary of what is in force today.
 */
export function LibraryView() {
  const { me, side, loading: viewerLoading } = useViewer();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const admin = canEditLibrary(me?.role);
  const asked = params.get("tab") as Tab | null;
  const tab: Tab = asked && TABS.includes(asked)
    && (admin || (asked !== "terms" && asked !== "import")) ? asked : "rules";
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    // Terms are admin-only on the API; asking as anyone else would only earn a 403.
    Promise.all([listRules(), listFacts(), admin ? listTerms() : Promise.resolve(null), listAssets(), listEvents(), listContacts()])
      .then(([rules, facts, terms, assets, events, contacts]) => {
        setData({ rules, facts, terms, assets, events, contacts });
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError && err.status === 503
        ? "The library needs the Verytas API. Connect it to manage rules, facts, terms and artwork."
        : (err as Error).message));
  }, [admin]);
  useEffect(() => { if (!viewerLoading && side === "manager") load(); }, [load, viewerLoading, side]);

  if (viewerLoading) return <ListSkeleton />;
  if (side === "creator") return <ForBrandTeam />;
  if (error) return <div className="vt-card p-6 text-sm text-muted">{error}</div>;
  if (!data) return <ListSkeleton />;

  const on = today();
  const latest = new Map<string, Rule>();
  for (const r of data.rules) if (!latest.has(r.code) || latest.get(r.code)!.version < r.version) latest.set(r.code, r);
  const rules = [...latest.values()];
  const tabs: { k: Tab; label: string; count: number | null; hint: string }[] = [
    { k: "rules", label: "Rules", count: rules.filter((r) => r.status === "active" && r.event_id == null).length,
      hint: `${rules.filter((r) => r.status === "draft").length} drafts` },
    { k: "facts", label: "Facts", count: data.facts.filter((f) => f.approved && f.valid_from <= on && (!f.valid_to || f.valid_to > on)).length,
      hint: "valid today" },
    { k: "events", label: "Events", count: data.events.filter((e) => e.live).length, hint: "running" },
    { k: "contacts", label: "Public contacts", count: data.contacts.filter((c) => c.active).length, hint: "listed" },
    ...(data.terms ? [{ k: "terms" as const, label: "Confidential terms", count: data.terms.filter((t) => !t.embargo_until || t.embargo_until > on).length,
      hint: "guarded" }] : []),
    { k: "assets", label: "Artwork", count: data.assets.filter((a) => a.active).length, hint: "official" },
    ...(admin ? [{ k: "import" as const, label: "Import", count: null, hint: "from a brand book" }] : []),
  ];
  const go = (k: Tab, state?: string) => {
    const q = new URLSearchParams();
    if (k !== "rules") q.set("tab", k);
    if (state) q.set("state", state);
    router.replace(q.size ? `${pathname}?${q}` : pathname, { scroll: false });
  };
  const onTabKey = tabKeys(tabs.map((t) => t.k), tab, (k) => go(k), "lib-tab");

  return (
    <div className="flex flex-col gap-5">
      <div role="tablist" aria-label="Library" onKeyDown={onTabKey} className="flex gap-1 overflow-x-auto border-b border-line">
        {tabs.map((t) => (
          <button key={t.k} id={`lib-tab-${t.k}`} type="button" role="tab" aria-selected={tab === t.k} aria-controls="lib-panel"
            tabIndex={tab === t.k ? 0 : -1} onClick={() => go(t.k)} title={t.count != null ? `${t.count} ${t.hint}` : t.hint}
            className={`-mb-px flex shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              tab === t.k ? "border-accent text-ink" : "border-transparent text-muted hover:text-ink"}`}>
            {t.label}
            {t.count != null && (
              <span className={`rounded-full px-1.5 text-[11px] tabular-nums ${tab === t.k ? "bg-accent/12 text-accent" : "bg-sunken text-subtle"}`}>{t.count}</span>
            )}
          </button>
        ))}
      </div>
      <div id="lib-panel" role="tabpanel" aria-labelledby={`lib-tab-${tab}`}>
        {!admin && <ReadOnlyNote />}
        {tab === "rules" && <RulesTab key={`${params.get("state")}-${params.get("q")}`} rules={data.rules.filter((r) => r.event_id == null)}
          editable={admin} onChanged={load} initialState={params.get("state")} initialQuery={params.get("q")} />}
        {tab === "events" && <EventsTab events={data.events} editable={admin} onChanged={load} />}
        {tab === "contacts" && <ContactsTab contacts={data.contacts} editable={admin} onChanged={load} />}
        {tab === "facts" && <FactsTab facts={data.facts} editable={admin} onChanged={load} />}
        {tab === "terms" && data.terms && <TermsTab terms={data.terms} onChanged={load} />}
        {tab === "assets" && <AssetsTab assets={data.assets} editable={admin} onChanged={load} />}
        {tab === "import" && admin && <ImportTab onAdded={(done) => { load(); if (done) go("rules", "draft"); }} />}
      </div>
    </div>
  );
}

/** Creators don't keep the library; they meet it as findings with citations in their reviews. */
export function ForBrandTeam() {
  return (
    <div className="vt-card flex flex-col items-start gap-3 p-6">
      <p className="text-sm font-semibold">This page is for the brand team</p>
      <p className="max-w-lg text-sm text-muted">
        The brand team keeps the rules and facts your posts are checked against. You will see them where they matter:
        every issue in a review cites the rule or fact behind it.
      </p>
      <Link href="/" className="vt-btn vt-btn-quiet">Back to my work</Link>
    </div>
  );
}

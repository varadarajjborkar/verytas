// The parts of the search bar that need no server: the console's own screens, settings and actions, the
// matching and highlighting shared by every result, the recently opened list, and the sample results shown
// when no API is connected. Anything about the workspace's data comes from GET /search instead.

import { canEditLibrary, type Side } from "./roles";
import type { SearchHit, SearchHitType } from "./types";

export type IconKey = "page" | "action" | "settings" | "sun" | "moon" | "monitor" | "signout" | "switch" | "recent" | SearchHitType;

export type ActionId = "theme:light" | "theme:dark" | "theme:system" | "settings:profile" | "settings:social"
  | "settings:theme" | "signout" | "switch:manager" | "switch:creator";
export type Target = { href: string } | { run: ActionId };

export type Entry = {
  id: string;
  group: "Actions" | "Pages" | "Settings";
  icon: IconKey;
  title: string;
  /** What it does or where it leads, in a few words. */
  sub: string;
  /** Extra words that should find it ("log out" finds Sign out). */
  keywords: string;
  target: Target;
};

export type Who = {
  side: Side;
  role: string | null | undefined;
  /** Sign-in is on for this server, so there is a session to end. Null until known. */
  signin: boolean | null;
  /** Sign-in is the shared demo's account picker. */
  demoSignin: boolean;
  canSwitch: boolean;
};

/** What each kind of server result is called, in the order the groups appear. */
export const TYPE_LABEL: Record<SearchHitType, string> = {
  content: "Pieces", finding: "Findings", escalation: "Escalations", creator: "Creators", rule: "Rules",
  fact: "Facts", term: "Confidential terms", asset: "Brand assets", event: "Events",
};
export const TYPE_ORDER = Object.keys(TYPE_LABEL) as SearchHitType[];

/** Headings for the suggestions the API returns for an empty query. */
export const SECTION_LABEL: Record<string, string> = {
  needs_changes: "Needs your changes", with_brand_team: "With the brand team", review_queue: "Review queue",
  open_escalations: "Open escalations", unclear_rules: "Unclear rules", recent: "Recent pieces",
};
export const SECTION_ORDER = Object.keys(SECTION_LABEL);

const page = (id: string, title: string, sub: string, href: string, keywords = ""): Entry =>
  ({ id, group: "Pages", icon: "page", title, sub, keywords, target: { href } });
const action = (id: string, title: string, sub: string, href: string, keywords: string): Entry =>
  ({ id, group: "Actions", icon: "action", title, sub, keywords, target: { href } });
const setting = (id: string, icon: IconKey, title: string, sub: string, run: ActionId, keywords: string): Entry =>
  ({ id, group: "Settings", icon, title, sub, keywords, target: { run } });

const CREATOR_PAGES = [
  page("home", "My work", "Your pieces and what each needs next", "/", "home overview"),
  page("reviews", "My reviews", "A new post and every review so far", "/review", "history submit check"),
  page("ask", "Ask Inki", "Questions about the brand guidelines", "/ask", "chat assistant help"),
  page("ai", "How AI is used", "Where models are involved and what they see", "/ai", "disclosure transparency privacy"),
];
const MANAGER_PAGES = [
  page("home", "Dashboard", "What needs a decision and how work flows", "/", "home overview"),
  page("queue", "Review queue", "Every creator's pieces, ranked by what needs you first", "/review", "pending approve reviews"),
  page("esc", "Escalations", "Requests creators raised to a person", "/escalations", "asks inbox"),
  page("creators", "Creators", "Everyone writing for the brand", "/creators", "people roster writers"),
  page("library", "Brand library", "Rules, facts, terms, events and artwork", "/library", "guidelines brand book"),
  page("health", "Guideline health", "Rules reviewers keep overriding", "/guidelines", "ambiguity unclear clarify"),
  page("ask", "Ask Inki", "Questions about the brand guidelines", "/ask", "chat assistant help"),
  page("ai", "How AI is used", "Where models are involved and what they see", "/ai", "disclosure transparency privacy"),
];
const LIBRARY_TABS = [
  page("lib-facts", "Facts", "Brand library · numbers posts may cite", "/library?tab=facts", "claims statistics figures"),
  page("lib-events", "Events", "Brand library · launches, sales and campaigns", "/library?tab=events", "campaign blackout"),
  page("lib-contacts", "Public contacts", "Brand library · phone numbers and handles that may appear", "/library?tab=contacts", "email phone"),
  page("lib-assets", "Artwork", "Brand library · official logos and marks", "/library?tab=assets", "logo mascot images brand assets"),
];

/** Everything a person on this side, in this role, can open or do from the bar without the server. */
export function staticEntries(who: Who): Entry[] {
  const admin = canEditLibrary(who.role);
  const out: Entry[] = [];
  if (who.side === "creator") {
    out.push(action("submit", "Submit a post", "My reviews · check a new piece before it goes out", "/review",
      "new post upload check write draft send review create"));
    out.push(...CREATOR_PAGES);
  } else {
    out.push(
      action("work-queue", "Work the review queue", "Review queue · pieces waiting for a decision", "/review", "pending approve decide"),
      action("open-esc", "Check open escalations", "Escalations · requests waiting for a person", "/escalations", "asks inbox"),
      action("fix-rules", "Fix unclear rules", "Guideline health · rules reviewers keep overriding", "/guidelines", "ambiguity clarify wording"),
    );
    if (admin) {
      out.push(
        action("add-rule", "Add a rule", "Brand library · rules", "/library", "new create guideline"),
        action("add-fact", "Add a fact", "Brand library · facts", "/library?tab=facts", "new create number claim"),
        action("add-term", "Add a confidential term", "Brand library · confidential terms", "/library?tab=terms", "new create secret codename embargo"),
        action("import", "Import a brand book", "Brand library · import", "/library?tab=import", "upload pdf guidelines extract"),
        action("add-event", "Plan a brand event", "Brand library · events", "/library?tab=events", "new campaign launch sale blackout"),
        action("add-asset", "Add official artwork", "Brand library · artwork", "/library?tab=assets", "upload logo mascot image"),
      );
    }
    out.push(...MANAGER_PAGES, ...LIBRARY_TABS);
    if (admin) out.push(page("lib-terms", "Confidential terms", "Brand library · words that must not leak", "/library?tab=terms", "secret codename embargo"));
  }
  out.push(
    setting("set-profile", "settings", "Profile and role", "Settings · name, role, clearance" + (admin ? ", join code" : ""),
      "settings:profile", "account email clearance" + (admin ? " join code invite creators" : "")),
    setting("set-social", "settings", "Social profiles", "Settings · the handles posts are checked against", "settings:social",
      "instagram linkedin x twitter youtube tiktok facebook handles"),
    setting("set-theme", "settings", "Appearance", "Settings · light, dark or follow the system", "settings:theme", "theme colour mode"),
    setting("theme-dark", "moon", "Dark theme", "Appearance · switch now", "theme:dark", "night mode appearance"),
    setting("theme-light", "sun", "Light theme", "Appearance · switch now", "theme:light", "day mode appearance"),
    setting("theme-system", "monitor", "Match system theme", "Appearance · follow the device", "theme:system", "auto automatic appearance"),
  );
  if (who.canSwitch) {
    out.push(who.side === "creator"
      ? setting("view-manager", "switch", "View as the brand team", "Settings · try the other side", "switch:manager", "switch persona role")
      : setting("view-creator", "switch", "View as a creator", "Settings · try the other side", "switch:creator", "switch persona role"));
  }
  if (who.signin) {
    out.push(setting("signout", "signout", who.demoSignin ? "Switch account" : "Sign out",
      who.demoSignin ? "Back to the account picker" : "End this session", "signout", "log out logout sign off leave exit"));
  }
  return out;
}

/** The entries offered before anything is typed: the next steps for this side, then the way to change look. */
export function suggestedEntries(who: Who): Entry[] {
  const ids = who.side === "creator" ? ["submit", "ask", "set-theme"] : ["work-queue", "open-esc", "fix-rules"];
  const all = staticEntries(who);
  return ids.map((id) => all.find((e) => e.id === id)).filter((e): e is Entry => Boolean(e));
}

const words = (s: string) => s.toLowerCase().split(/\s+/).filter(Boolean);

/** Entries whose title or keywords contain every word typed, title prefixes first. */
export function matchEntries(entries: Entry[], q: string, limit: number): Entry[] {
  const terms = words(q);
  if (!terms.length) return [];
  const scored: { e: Entry; score: number }[] = [];
  for (const e of entries) {
    const title = e.title.toLowerCase();
    const hay = `${title} ${e.sub.toLowerCase()} ${e.keywords}`;
    if (!terms.every((t) => hay.includes(t))) continue;
    const score = title.startsWith(terms[0]) ? 0 : title.includes(` ${terms[0]}`) ? 1 : title.includes(terms[0]) ? 2 : 3;
    scored.push({ e, score });
  }
  return scored.sort((a, b) => a.score - b.score).slice(0, limit).map((s) => s.e);
}

/** The text cut into plain and matched runs, for highlighting what was typed. */
export function highlight(text: string, q: string): { text: string; hit: boolean }[] {
  const terms = [...new Set(words(q))].sort((a, b) => b.length - a.length);
  if (!terms.length) return [{ text, hit: false }];
  const re = new RegExp(`(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(re).filter(Boolean).map((part, i) => ({ text: part, hit: i % 2 === 1 }));
}

/** Where a result leads, as a short name, from its link. */
export function destination(href: string): string {
  const [path, query = ""] = href.split("?");
  const params = new URLSearchParams(query);
  switch (path) {
    case "/": return "Home";
    case "/review": return "Review";
    case "/escalations": return "Escalations";
    case "/creators": return "Creators";
    case "/guidelines": return "Guideline health";
    case "/ask": return "Ask Inki";
    case "/ai": return "How AI is used";
    case "/library": {
      const tab = params.get("tab") ?? "rules";
      return `Library · ${({ rules: "Rules", facts: "Facts", events: "Events", contacts: "Contacts", terms: "Terms",
        assets: "Artwork", import: "Import" } as Record<string, string>)[tab] ?? "Rules"}`;
    }
    default: return "Open";
  }
}

const ORIGIN = "http://vt.invalid";

/** Only in-app links are followed, whatever a response contains. A backslash or a tab inside the first
 * characters turns "/\\host" into "//host" for the browser, so the link is resolved the way the browser
 * would and refused if it leaves the origin. */
export const safeHref = (href: string) => {
  if (!href.startsWith("/") || href.startsWith("//")) return false;
  try {
    return new URL(href, ORIGIN).origin === ORIGIN;
  } catch {
    return false;
  }
};

// --- recently opened ---------------------------------------------------------------------------

/** What was opened is a person's own trail: titles and counts of pieces their clearance let them see. It is kept
 * per account, so another person on the same browser (the demo's account picker) never reads it. */
export const recentKey = (owner: number | "demo" | null | undefined) => `vt-search-recent:${owner ?? "none"}`;
/** The key before the list was per account; its content may belong to anyone, so it is only ever deleted. */
export const LEGACY_RECENT_KEY = "vt-search-recent";
const RECENT_MAX = 5;

export function parseRecent(raw: string | null): SearchHit[] {
  try {
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list)
      ? list.filter((h): h is SearchHit => typeof h?.title === "string" && typeof h?.href === "string" && safeHref(h.href))
        .slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

/** The list with `hit` moved to the front. Suggestion sections are dropped: a recent item is just an item. */
export function withRecent(raw: string | null, hit: SearchHit): string {
  const rest = parseRecent(raw).filter((h) => !(h.type === hit.type && h.id === hit.id));
  return JSON.stringify([{ ...hit, section: undefined }, ...rest].slice(0, RECENT_MAX));
}

// --- sample results (no API connected) -----------------------------------------------------------

/** What the bar offers when the console runs on sample data: the sample review's piece and findings, and
 * the sample rules. Imported on demand so the sample data is not part of every page. */
export async function demoHits(q: string, side: Side): Promise<SearchHit[]> {
  const { demoHealth, demoReview } = await import("./demo-data");
  const piece: SearchHit = { type: "content", id: 0, title: "Q3 launch post (sample)", subtitle: "linkedin · Changes requested",
    href: "/review" };
  const findings: SearchHit[] = demoReview.findings.map((f) => ({ type: "finding" as const, id: f.id, title: f.title,
    subtitle: `${f.level} · in ${piece.title}`, href: "/review" }));
  const rules: SearchHit[] = side === "creator" ? [] : demoHealth.map((h) => ({ type: "rule" as const, id: h.rule_id,
    title: `${h.code} · ${h.title}`, subtitle: `${h.severity} · active`, href: "/guidelines" }));
  if (!q.trim()) {
    return [{ ...piece, section: "recent" }, ...(side === "creator" ? [] : rules.filter((_, i) => demoHealth[i].ambiguity != null
      && demoHealth[i].ambiguity >= 0.5).map((r) => ({ ...r, section: "unclear_rules" })))];
  }
  const terms = words(q);
  const has = (h: SearchHit) => terms.every((t) => `${h.title} ${h.subtitle}`.toLowerCase().includes(t));
  return [piece, ...findings, ...rules].filter(has).slice(0, 12);
}

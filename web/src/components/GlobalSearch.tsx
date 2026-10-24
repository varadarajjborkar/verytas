"use client";

import { useRouter } from "next/navigation";
import {
  type ComponentType, type KeyboardEvent, useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore,
} from "react";
import { ApiError, search } from "@/lib/review-client";
import type { Side } from "@/lib/roles";
import {
  type ActionId, type Entry, type IconKey, LEGACY_RECENT_KEY, matchEntries, parseRecent, recentKey, safeHref, SECTION_LABEL, SECTION_ORDER,
  staticEntries, suggestedEntries, type Target, TYPE_LABEL, TYPE_ORDER, type Who, withRecent, destination, demoHits, highlight,
} from "@/lib/search";
import { useStored, writeStored } from "@/lib/stored";
import type { SearchHit } from "@/lib/types";
import {
  AlertIcon, ArrowRightIcon, BookIcon, CalendarIcon, CloseIcon, EnterIcon, HistoryIcon, ImageIcon, InboxIcon, InfoIcon,
  LogOutIcon, MonitorIcon, MoonIcon, PanelIcon, ReviewIcon, SearchIcon, SettingsIcon, ShieldIcon, SparkIcon, SunIcon, UsersIcon,
} from "./Icons";
import { type ThemeChoice, useTheme } from "./Providers";
import { OPEN_SETTINGS } from "./SettingsMenu";
import { useToast } from "./Toaster";
import { useViewer } from "./Viewer";

const ICON: Record<IconKey, ComponentType<{ size?: number }>> = {
  page: PanelIcon, action: SparkIcon, settings: SettingsIcon, sun: SunIcon, moon: MoonIcon, monitor: MonitorIcon,
  signout: LogOutIcon, switch: UsersIcon, recent: HistoryIcon, content: ReviewIcon, finding: AlertIcon, escalation: InboxIcon,
  creator: UsersIcon, rule: BookIcon, fact: InfoIcon, term: ShieldIcon, asset: ImageIcon, event: CalendarIcon,
};

/** Typing settles for this long before a request goes out, so a word costs one call rather than one per key. */
const DEBOUNCE_MS = 160;
const PER_GROUP = 5;
const STATIC_SHOWN = { Actions: 3, Pages: 4, Settings: 3 } as const;

type Item = { key: string; icon: IconKey; title: string; sub: string; where: string; target: Target; hit?: SearchHit };
type Group = { id: string; label: string; items: Item[] };
type Remote = { q: string; hits: SearchHit[]; failed: boolean };

const WHERE_RUN: Record<ActionId, string> = {
  "theme:light": "Appearance", "theme:dark": "Appearance", "theme:system": "Appearance", "settings:profile": "Settings",
  "settings:social": "Settings", "settings:theme": "Settings", signout: "Account", "switch:manager": "Account",
  "switch:creator": "Account",
};

const fromEntry = (e: Entry): Item => ({
  key: `s:${e.id}`, icon: e.icon, title: e.title, sub: e.sub, target: e.target,
  where: "href" in e.target ? destination(e.target.href) : WHERE_RUN[e.target.run],
});
const fromHit = (h: SearchHit, k: string): Item => ({
  key: `${k}:${h.type}:${h.id}`, icon: h.type, title: h.title, sub: h.subtitle, target: { href: h.href }, hit: h,
  where: destination(h.href),
});

/** True once this server has said it has no API configured; from then on the bar answers from sample data
 * without asking. That cannot change while the page is open, unlike an API that is merely down. */
let sampleMode = false;

/** The proxy's own answer when no API is configured. Any other 503 is the API failing: an error to show and
 * to retry on the next query, not a reason to invent results. */
const isDemoRefusal = (err: unknown) => err instanceof ApiError && err.status === 503
  && (err.detail as { demo?: unknown } | null | undefined)?.demo === true;

async function fetchHits(q: string, side: Side, signal: AbortSignal): Promise<SearchHit[]> {
  if (!sampleMode) {
    try {
      return (await search(q, q ? PER_GROUP : 3, signal)).results;
    } catch (err) {
      if (signal.aborted || !isDemoRefusal(err)) throw err;
      sampleMode = true;
    }
  }
  return demoHits(q, side);
}

function buildGroups(q: string, who: Who, remote: Remote | null, recent: SearchHit[]): Group[] {
  if (!q) {
    const groups: Group[] = [{ id: "suggested", label: "Suggested", items: suggestedEntries(who).map(fromEntry) }];
    const seen = new Set<string>();
    for (const key of SECTION_ORDER) {
      const items = (remote?.hits ?? []).filter((h) => (h.section ?? "recent") === key);
      items.forEach((h) => seen.add(`${h.type}:${h.id}`));
      if (items.length) groups.push({ id: key, label: SECTION_LABEL[key], items: items.map((h) => fromHit(h, key)) });
    }
    const opened = recent.filter((h) => !seen.has(`${h.type}:${h.id}`));
    if (opened.length) groups.push({ id: "recently", label: "Recently opened", items: opened.map((h) => fromHit(h, "r")) });
    return groups;
  }
  const matched = matchEntries(staticEntries(who), q, 40);
  const groups: Group[] = (["Actions", "Pages", "Settings"] as const).map((label) => ({
    id: label.toLowerCase(), label, items: matched.filter((e) => e.group === label).slice(0, STATIC_SHOWN[label]).map(fromEntry),
  }));
  for (const type of TYPE_ORDER) {
    const items = (remote?.hits ?? []).filter((h) => h.type === type);
    if (items.length) groups.push({ id: type, label: TYPE_LABEL[type], items: items.map((h) => fromHit(h, "h")) });
  }
  return groups.filter((g) => g.items.length);
}

function Marked({ text, q }: { text: string; q: string }) {
  return <>{highlight(text, q).map((p, i) => (p.hit ? <mark key={i} className="vt-hit">{p.text}</mark> : p.text))}</>;
}

const noSubscribe = () => () => {};
const isApple = () => /Mac|iPhone|iPad/.test(navigator.userAgent);

/**
 * The bar at the top of every screen: one box that finds pages, settings and actions on the console's side,
 * and, from the API, the pieces, findings, escalations, people and library entries the signed-in person may
 * open. Empty, it suggests what needs them next. It is a combobox over a listbox: the focus stays in the
 * input while the arrow keys move a highlighted option, so a screen reader hears each result as it is reached.
 * On a phone it is an icon that opens a full-width bar.
 */
export function GlobalSearch() {
  const router = useRouter();
  const toast = useToast();
  const { setChoice } = useTheme();
  const viewer = useViewer();
  const { me, side, app, loading, canSwitch, switchTo, demo } = viewer;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [remote, setRemote] = useState<Remote | null>(null);
  const [session, setSession] = useState<{ required: boolean; demo: boolean } | null>(null);
  // Without an account (the sample-data demo) there is one reader; with sign-in still loading, nothing is kept.
  const owner = me?.id ?? (demo ? "demo" : null);
  const storeKey = recentKey(owner);
  const rawRecent = useStored(storeKey);
  const recent = useMemo(() => parseRecent(rawRecent), [rawRecent]);
  const mod = useSyncExternalStore(noSubscribe, () => (isApple() ? "⌘" : "Ctrl"), () => "Ctrl");

  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const wrapper = useRef<HTMLDivElement>(null);
  const openNow = useRef(false);
  const restoreTo = useRef<HTMLElement | null>(null);

  const q = query.trim();
  const ready = !loading || Boolean(app);

  const openBar = useCallback((from: Element | null) => {
    if (openNow.current) return;
    openNow.current = true;
    restoreTo.current = from instanceof HTMLElement && !wrapper.current?.contains(from) ? from : null;
    setOpen(true);
  }, []);
  const close = useCallback((restore: boolean) => {
    openNow.current = false;
    setOpen(false);
    setQuery("");
    setActive(0);
    input.current?.blur();
    if (restore) restoreTo.current?.focus();
  }, []);

  // Cmd/Ctrl+K from anywhere, and "/" when no field is being typed in. A modal dialog owns the keyboard.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (document.querySelector("[data-vt-modal]")) return;
      const target = e.target as HTMLElement | null;
      const typing = Boolean(target?.isContentEditable) || /^(INPUT|TEXTAREA|SELECT)$/.test(target?.tagName ?? "");
      const palette = (e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "k";
      const slash = e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !typing;
      if (!palette && !slash) return;
      e.preventDefault();
      openBar(document.activeElement);
      input.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openBar]);

  // The phone's bar covers the page, so the page behind stays still while it is open.
  useEffect(() => {
    if (!open || !window.matchMedia("(max-width: 47.99rem)").matches) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = overflow; };
  }, [open]);

  // The list used to live under one shared key whose content may belong to anyone, so it is only ever dropped.
  useEffect(() => { writeStored(LEGACY_RECENT_KEY, null); }, []);

  // Whether there is a session to end, learned the first time the bar opens.
  useEffect(() => {
    if (!open || session) return;
    fetch("/api/session").then((r) => r.json()).then((j) => setSession({ required: Boolean(j.required), demo: Boolean(j.demo) }))
      .catch(() => setSession({ required: false, demo: false }));
  }, [open, session]);

  // The API is asked once the typing settles, and a request nobody is waiting for any more is cancelled.
  // One character is too broad to be worth a round trip: it matches the pages and actions only.
  const wantsRemote = q.length !== 1;
  useEffect(() => {
    if (!open || !wantsRemote || !ready) return;
    const ctl = new AbortController();
    const t = setTimeout(() => {
      fetchHits(q, side, ctl.signal)
        .then((hits) => setRemote({ q, hits, failed: false }))
        .catch(() => { if (!ctl.signal.aborted) setRemote({ q, hits: [], failed: true }); });
    }, q ? DEBOUNCE_MS : 0);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [open, q, wantsRemote, ready, side]);

  // The previous answer stays up while the next one is on its way, so the list does not blink between keys.
  const shown = wantsRemote && remote && (q ? remote.q !== "" : remote.q === "") ? remote : null;
  const pending = open && wantsRemote && ready && remote?.q !== q;
  // While the answer for what is typed now is on its way, the hits still listed answer an older query. They
  // stay up so the list does not blink, but they cannot be opened: Enter would land on the wrong thing.
  const staleHits = pending && q !== "";

  const who = useMemo<Who>(() => ({
    side, role: me?.role, signin: session?.required ?? null, demoSignin: Boolean(session?.demo), canSwitch,
  }), [side, me?.role, session, canSwitch]);
  const groups = useMemo(() => (ready ? buildGroups(q, who, shown, recent) : []), [ready, q, who, shown, recent]);
  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const idx = Math.min(active, Math.max(flat.length - 1, 0));
  const optionId = (i: number) => `${listId}-o-${i}`;

  useEffect(() => {
    if (open) document.getElementById(`${listId}-o-${idx}`)?.scrollIntoView({ block: "nearest" });
  }, [open, idx, listId]);

  async function run(id: ActionId) {
    if (id.startsWith("theme:")) {
      const choice = id.slice(6) as ThemeChoice;
      setChoice(choice);
      toast({ kind: "success", title: choice === "system" ? "Following the system theme" : `${choice === "dark" ? "Dark" : "Light"} theme on` });
    } else if (id.startsWith("settings:")) {
      window.dispatchEvent(new CustomEvent(OPEN_SETTINGS, { detail: id.slice(9) }));
    } else if (id === "signout") {
      writeStored(storeKey, null);
      await fetch("/api/session", { method: "DELETE" }).catch(() => null);
      router.replace("/signin");
      router.refresh();
    } else {
      await switchTo(id.slice(7) as Side).catch((err: Error) => toast({ kind: "error", title: "Couldn't switch", detail: err.message }));
    }
  }

  function choose(item: Item) {
    if (item.hit && staleHits) return;
    close(false);
    const t = item.target;
    if ("run" in t) {
      void run(t.run);
      return;
    }
    if (!safeHref(t.href)) return;
    if (item.hit && owner !== null) writeStored(storeKey, withRecent(rawRecent, item.hit));
    router.push(t.href);
  }

  function onInputKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!openNow.current) return openBar(null);
      if (flat.length) setActive((idx + (e.key === "ArrowDown" ? 1 : -1) + flat.length) % flat.length);
    } else if (e.key === "Enter" && open && flat[idx]) {
      e.preventDefault();
      choose(flat[idx]);
    }
  }

  const status = !ready ? "Getting things ready" : pending ? "Searching" : `${flat.length} ${flat.length === 1 ? "result" : "results"}`;

  return (
    <>
      {open && (
        <div aria-hidden onClick={() => close(true)}
          className="pointer-events-auto fixed inset-0 z-40 bg-[var(--vt-glass-scrim)] backdrop-blur-[2px] md:bg-transparent md:backdrop-blur-none" />
      )}
      <button type="button" aria-label="Search" aria-keyshortcuts="Control+K Meta+K /" onClick={(e) => { openBar(e.currentTarget); requestAnimationFrame(() => input.current?.focus()); }}
        className={`vt-glass pointer-events-auto grid h-10 w-10 place-items-center rounded-full text-ink md:hidden ${open ? "hidden" : ""}`}>
        <SearchIcon size={18} />
      </button>
      <div ref={wrapper} onKeyDown={(e) => { if (e.key === "Escape" && open) { e.preventDefault(); close(true); } }}
        onBlur={(e) => { if (open && e.relatedTarget instanceof Node && !wrapper.current?.contains(e.relatedTarget)) close(false); }}
        className={`pointer-events-auto relative z-50 w-full max-w-[34rem] ${open
          ? "max-md:fixed max-md:inset-x-3 max-md:top-3 max-md:w-auto max-md:max-w-none" : "max-md:hidden"}`}>
        {/* The whole pill is the field: a press on the icon, the padding or the shortcut hint focuses the input
            (its own buttons keep their clicks), and preventDefault keeps that press from blurring it first. */}
        <div onMouseDown={(e) => {
          if (e.target === input.current || (e.target as HTMLElement).closest("button")) return;
          e.preventDefault();
          input.current?.focus();
        }}
          className="vt-glass flex h-11 cursor-text items-center gap-2.5 rounded-full pl-4 pr-2 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent md:h-10">
          <SearchIcon size={17} className="shrink-0 text-muted" />
          <input ref={input} type="text" role="combobox" aria-expanded={open} aria-controls={listId} aria-autocomplete="list"
            aria-activedescendant={open && flat.length ? optionId(idx) : undefined} aria-label="Search everything"
            aria-keyshortcuts="Control+K Meta+K /" value={query} placeholder="Search pages, pieces, rules, settings…" enterKeyHint="go"
            autoComplete="off" autoCorrect="off" autoCapitalize="off" spellCheck={false}
            onFocus={(e) => openBar(e.relatedTarget)}
            onChange={(e) => { setQuery(e.target.value); setActive(0); }} onKeyDown={onInputKey}
            className="min-w-0 flex-1 bg-transparent text-base text-ink outline-none placeholder:text-subtle md:text-sm" />
          {open && query && (
            <button type="button" aria-label="Clear search" onMouseDown={(e) => e.preventDefault()}
              onClick={() => { setQuery(""); setActive(0); input.current?.focus(); }}
              className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted hover:bg-[var(--vt-glass-hover)] hover:text-ink">
              <CloseIcon size={14} />
            </button>
          )}
          {open
            ? <button type="button" onClick={() => close(true)} className="shrink-0 rounded-full px-2.5 py-1 text-sm font-medium text-accent md:hidden">Cancel</button>
            : <span aria-hidden className="mr-1 hidden shrink-0 items-center gap-1 md:flex"><kbd className="vt-kbd">{mod}</kbd><kbd className="vt-kbd">K</kbd></span>}
        </div>

        {open && (
          <div className="vt-glass vt-glass-strong vt-pop absolute inset-x-0 top-full mt-2 origin-top overflow-hidden rounded-[1.75rem]">
            <p role="status" aria-live="polite" className="sr-only">{status}</p>
            <div className="flex max-h-[min(30rem,calc(100dvh-7rem))] flex-col">
              {shown?.failed && (
                <p className="mx-4 mt-3 rounded-xl bg-[var(--vt-warning-bg)] px-3 py-2 text-xs text-[var(--vt-warning)]">
                  The workspace couldn&apos;t be searched just now. Pages, settings and actions still work.
                </p>
              )}
              {flat.length > 0 ? (
                <div id={listId} role="listbox" aria-label="Search results" aria-busy={pending}
                  className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-2">
                  {groups.map((g) => (
                    <div key={g.id} role="group" aria-labelledby={`${listId}-g-${g.id}`} className="py-1 first:pt-0">
                      <div id={`${listId}-g-${g.id}`} role="presentation"
                        className="px-3 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wider text-subtle">{g.label}</div>
                      {g.items.map((item) => {
                        const i = flat.indexOf(item);
                        const Ico = ICON[item.icon];
                        return (
                          <div key={item.key} id={optionId(i)} role="option" aria-selected={i === idx}
                            aria-disabled={item.hit && staleHits ? true : undefined}
                            onMouseMove={() => { if (i !== idx) setActive(i); }} onMouseDown={(e) => e.preventDefault()}
                            onClick={() => choose(item)}
                            className="group flex cursor-pointer items-center gap-3 rounded-2xl px-2.5 py-2.5 aria-selected:bg-[var(--vt-glass-active)] aria-disabled:opacity-60 md:py-2">
                            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[var(--vt-glass-hover)] text-muted group-aria-selected:bg-accent group-aria-selected:text-accent-ink">
                              <Ico size={17} />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium"><Marked text={item.title} q={q} /></span>
                              <span className="block truncate text-xs text-muted">
                                <Marked text={item.sub} q={q} />{item.hit && <span className="sm:hidden"> · {item.where}</span>}
                              </span>
                            </span>
                            <span className="hidden shrink-0 items-center gap-1.5 text-[11px] text-subtle sm:flex">
                              {item.where}
                              {i === idx ? <EnterIcon size={13} /> : <ArrowRightIcon size={13} />}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="px-6 py-8 text-center text-sm text-muted">
                  {!ready ? "Getting things ready…" : pending ? "Searching…" : q
                    ? <>Nothing matches &ldquo;{q}&rdquo;. Try a piece title, a rule code, a creator or a page name.</>
                    : "Nothing to suggest yet. Start typing to search."}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

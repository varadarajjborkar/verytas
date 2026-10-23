"use client";

import { useRouter } from "next/navigation";
import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useStored, writeStored } from "@/lib/stored";
import { CloseIcon, SettingsIcon } from "./Icons";
import { type ThemeChoice, useTheme } from "./Providers";
import { useToast } from "./Toaster";
import { useViewer } from "./Viewer";

type Me = { id: number; email: string; name: string; role: string; clearance: string };
const SOCIAL_KEY = "vt-social-profiles";
const PLATFORMS = [
  { key: "instagram", label: "Instagram", placeholder: "@yourbrand" },
  { key: "x", label: "X", placeholder: "@yourbrand" },
  { key: "linkedin", label: "LinkedIn", placeholder: "linkedin.com/company/yourbrand" },
  { key: "youtube", label: "YouTube", placeholder: "@yourbrand" },
  { key: "tiktok", label: "TikTok", placeholder: "@yourbrand" },
  { key: "facebook", label: "Facebook", placeholder: "facebook.com/yourbrand" },
  { key: "other", label: "Other", placeholder: "Any other app or site" },
];
const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];
const TABS = [
  { value: "profile", label: "Profile" },
  { value: "social", label: "Socials" },
  { value: "theme", label: "Appearance" },
] as const;
export type SettingsTab = (typeof TABS)[number]["value"];
type Tab = SettingsTab;

/** Dispatched on window (detail: a tab) by anything that wants Settings opened there, such as the search bar. */
export const OPEN_SETTINGS = "vt-open-settings";

/** The settings button, and the settings window it opens over a blurred page. */
export function SettingsMenu({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [first, setFirst] = useState<Tab>("profile");
  const button = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    button.current?.focus();
  }, []);

  useEffect(() => {
    const onOpen = (e: Event) => {
      // The phone header and the sidebar each mount a menu; only the one on screen answers.
      if (!button.current || button.current.offsetParent === null) return;
      const tab = (e as CustomEvent<string>).detail;
      setFirst(TABS.some((t) => t.value === tab) ? (tab as Tab) : "profile");
      setOpen(true);
    };
    window.addEventListener(OPEN_SETTINGS, onOpen);
    return () => window.removeEventListener(OPEN_SETTINGS, onOpen);
  }, []);

  return (
    <>
      <button ref={button} type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}
        aria-label="Settings"
        className={compact
          ? "grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-sunken hover:text-ink"
          : "group flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-muted transition hover:bg-sunken hover:text-ink"}>
        <SettingsIcon size={compact ? 20 : 18} strokeWidth={1.75}
          className="shrink-0 transition-transform duration-500 ease-out group-hover:rotate-45" />
        {!compact && <span className="text-sm font-medium">Settings</span>}
      </button>
      {open && <SettingsDialog onClose={close} first={first} />}
    </>
  );
}

function SettingsDialog({ onClose, first }: { onClose: () => void; first: Tab }) {
  const [tab, setTab] = useState<Tab>(first);
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [signin, setSignin] = useState<boolean | null>(null);
  const [demo, setDemo] = useState(false);
  const [joinCode, setJoinCode] = useState<string | null>(null);
  const saved = useStored(SOCIAL_KEY);
  const savedSocials = useMemo<Record<string, string>>(() => {
    try {
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  }, [saved]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const socials = { ...savedSocials, ...edits };
  const { choice, setChoice } = useTheme();
  const viewer = useViewer();
  const [switching, setSwitching] = useState(false);
  const toast = useToast();
  const router = useRouter();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const ids = useId();

  useEffect(() => {
    fetch("/api/session").then((r) => r.json()).then((j) => { setSignin(Boolean(j.required)); setDemo(Boolean(j.demo)); })
      .catch(() => setSignin(false));
    fetch("/api/v/me").then(async (r) => {
      if (!r.ok) {
        setMeError(r.status === 503 ? "Demo mode: no account is connected." : "Couldn't load the account.");
        return;
      }
      const who: Me = await r.json();
      setMe(who);
      // Only a company made by signing up has one; seeded workspaces answer 404.
      if (who.role === "brand_admin") {
        const code = await fetch("/api/v/accounts/join-code").then((c) => (c.ok ? c.json() : null)).catch(() => null);
        setJoinCode(code?.join_code ?? null);
      }
    }).catch(() => setMeError("Couldn't load the account."));
  }, []);

  // Modal behaviour: focus moves in and stays in, Escape closes, and the page
  // behind is inert (no clicks, no focus, hidden from screen readers) and still.
  useEffect(() => {
    const el = panel.current;
    if (!el) return;
    const root = el.closest<HTMLElement>("[data-vt-modal]");
    el.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    const focusable = () => [...el.querySelectorAll<HTMLElement>(
      "button:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex='-1'])")];
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      if (e.key !== "Tab") return;
      const items = focusable();
      const first = items[0], last = items[items.length - 1];
      const inside = el.contains(document.activeElement);
      if (e.shiftKey && (!inside || document.activeElement === first)) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && (!inside || document.activeElement === last)) { e.preventDefault(); first?.focus(); }
    };
    const others = [...document.body.children].filter((c): c is HTMLElement => c !== root && c instanceof HTMLElement
      && !["SCRIPT", "STYLE"].includes(c.tagName) && !c.inert);
    others.forEach((c) => { c.inert = true; });
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    return () => {
      others.forEach((c) => { c.inert = false; });
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  /** Arrow keys move between options of a tablist or radiogroup, as WAI-ARIA expects. */
  function arrows<T>(e: ReactKeyboardEvent, values: readonly T[], current: T, pick: (v: T) => void) {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    const to = e.key === "Home" ? 0 : e.key === "End" ? values.length - 1
      : step ? (values.indexOf(current) + step + values.length) % values.length : -1;
    if (to < 0) return;
    e.preventDefault();
    // currentTarget is cleared once the handler returns, so hold on to it for the next frame.
    const group = e.currentTarget as HTMLElement;
    pick(values[to]);
    requestAnimationFrame(() => group.querySelector<HTMLElement>("[aria-selected='true'], [aria-checked='true']")?.focus());
  }

  function saveSocials() {
    if (writeStored(SOCIAL_KEY, JSON.stringify(socials))) {
      setEdits({});
      toast({ kind: "success", title: "Socials saved" });
    } else {
      toast({ kind: "error", title: "Couldn't save", detail: "This browser is blocking local storage" });
    }
  }

  async function switchSide(side: "manager" | "creator") {
    setSwitching(true);
    try {
      await viewer.switchTo(side);
    } catch (err) {
      setSwitching(false);
      toast({ kind: "error", title: "Couldn't switch", detail: (err as Error).message });
    }
  }

  async function signOut() {
    await fetch("/api/session", { method: "DELETE" }).catch(() => null);
    onClose();
    router.replace("/signin");
    router.refresh();
  }

  const initials = (me?.name ?? "You").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return createPortal(
    <div data-vt-modal className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        // One fixed size (60% of the window wide, 70% tall) so switching tabs never resizes it.
        className="vt-pop relative flex h-[min(70dvh,calc(100dvh-2rem))] min-h-[24rem] w-full max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)] md:w-[60vw] md:max-w-[64rem]">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <h2 id={titleId} className="text-base font-semibold">Settings</h2>
          <button type="button" onClick={onClose} aria-label="Close settings"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
            <CloseIcon size={16} />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <div role="tablist" aria-label="Settings sections" aria-orientation="vertical"
          className="mx-5 mt-4 grid grid-cols-3 gap-1 rounded-xl bg-sunken p-1 text-[13px] font-medium md:m-0 md:flex md:w-52 md:shrink-0 md:flex-col md:gap-0.5 md:rounded-none md:border-r md:border-line md:bg-transparent md:p-3"
          onKeyDown={(e) => arrows(e, TABS.map((t) => t.value), tab, setTab)}>
          {TABS.map((t, i) => (
            <button key={t.value} role="tab" type="button" aria-selected={tab === t.value} onClick={() => setTab(t.value)}
              id={`${ids}-tab-${t.value}`} aria-controls={`${ids}-panel`} tabIndex={tab === t.value ? 0 : -1}
              data-autofocus={i === 0 ? true : undefined}
              className={`rounded-lg px-2 py-1.5 transition md:px-3 md:py-2 md:text-left md:text-sm ${tab === t.value
                ? "bg-raised text-ink shadow-[var(--vt-shadow)] md:bg-accent/12 md:shadow-none" : "text-muted hover:text-ink md:hover:bg-sunken"}`}>
              {t.label}
            </button>
          ))}
        </div>

        <div id={`${ids}-panel`} role="tabpanel" aria-labelledby={`${ids}-tab-${tab}`}
          className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4 md:px-7 md:py-6">
          {tab === "profile" && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <span aria-hidden className="vt-mark grid h-11 w-11 place-items-center rounded-full text-sm font-semibold">{initials}</span>
                <div className="min-w-0">
                  <p className="truncate font-medium">{me?.name ?? (meError ? "Not connected" : "Loading…")}</p>
                  <p className="truncate text-sm text-muted">{me?.email ?? meError ?? ""}</p>
                </div>
              </div>
              {me && (
                <dl className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-sunken px-3 py-2.5">
                    <dt className="text-xs text-muted">Role</dt>
                    <dd className="mt-0.5 text-sm font-medium capitalize">{me.role.replace("_", " ")}</dd>
                  </div>
                  <div className="rounded-xl bg-sunken px-3 py-2.5">
                    <dt className="text-xs text-muted">Clearance</dt>
                    <dd className="mt-0.5 text-sm font-medium capitalize">{me.clearance}</dd>
                  </div>
                </dl>
              )}
              {joinCode && (
                <div className="rounded-xl border border-line p-3">
                  <p className="text-sm font-medium">Join code for your creators</p>
                  <p className="mt-0.5 text-xs text-muted">They enter it when they create their account on the sign-in page.</p>
                  <p className="mt-2 select-all font-mono text-lg font-semibold tracking-[0.3em]">{joinCode}</p>
                </div>
              )}
              <p className="text-xs leading-5 text-muted">
                {signin ? "Signed in with your own account." : "Using a workspace demo account."}
              </p>
              {viewer.canSwitch && (
                <div className="rounded-xl border border-line p-3">
                  <p className="text-sm font-medium">View as</p>
                  <p className="mt-0.5 text-xs text-muted">Sign-in is off, so this browser can try either side. Each is a real account with its own permissions.</p>
                  <div role="radiogroup" aria-label="View as" className="mt-3 inline-grid grid-cols-2 gap-1 rounded-lg bg-sunken p-0.5 text-xs font-medium"
                    onKeyDown={(e) => arrows(e, ["manager", "creator"] as const, viewer.side, (v) => { if (v !== viewer.side) void switchSide(v); })}>
                    {([["manager", "Brand team"], ["creator", "Creator"]] as const).map(([v, l]) => (
                      <button key={v} type="button" role="radio" aria-checked={viewer.side === v} tabIndex={viewer.side === v ? 0 : -1}
                        disabled={switching} onClick={() => { if (v !== viewer.side) void switchSide(v); }}
                        className={`rounded-md px-4 py-1.5 transition ${viewer.side === v ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
                        {l}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {me && signin && (
                <button type="button" onClick={signOut} className="vt-btn vt-btn-quiet self-start">{demo ? "Switch account" : "Sign out"}</button>
              )}
            </div>
          )}

          {tab === "social" && (
            <div className="flex flex-col gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                {PLATFORMS.map((pl) => (
                  <label key={pl.key} className="flex flex-col gap-1 text-xs font-medium text-muted">
                    {pl.label}
                    <input className="vt-input" value={socials[pl.key] ?? ""} placeholder={pl.placeholder} maxLength={120}
                      onChange={(e) => setEdits((x) => ({ ...savedSocials, ...x, [pl.key]: e.target.value }))} />
                  </label>
                ))}
              </div>
              <button type="button" onClick={saveSocials} className="vt-btn vt-btn-primary self-end">Save</button>
            </div>
          )}

          {tab === "theme" && (
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-3"
              onKeyDown={(e) => arrows(e, THEMES.map((t) => t.value), choice, setChoice)}>
              {THEMES.map((th) => (
                <button key={th.value} type="button" role="radio" aria-checked={choice === th.value}
                  tabIndex={choice === th.value ? 0 : -1} onClick={() => setChoice(th.value)}
                  className={`flex flex-col gap-2 rounded-xl border p-2 text-left text-sm transition ${choice === th.value ? "border-accent ring-2 ring-accent/25" : "border-line hover:border-line-strong"}`}>
                  <ThemeSwatch kind={th.value} />
                  <span className="px-0.5 font-medium">{th.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}

function ThemeSwatch({ kind }: { kind: ThemeChoice }) {
  const pane = (bg: string, card: string, accent: string) => (
    <span className="flex h-full w-full flex-col gap-1 p-1.5" style={{ background: bg }}>
      <span className="h-1.5 w-8 rounded-full" style={{ background: accent }} />
      <span className="flex-1 rounded" style={{ background: card }} />
    </span>
  );
  const light = pane("#eceef2", "#f6f7f9", "#1a5fd1");
  const dark = pane("#0c0e13", "#1a1e27", "#4c9bff");
  return (
    <span aria-hidden className="flex h-14 w-full overflow-hidden rounded-lg border border-line">
      {kind === "light" ? light : kind === "dark" ? dark : <>{light}{dark}</>}
    </span>
  );
}

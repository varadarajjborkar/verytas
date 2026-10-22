"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useStored, writeStored } from "@/lib/stored";
import { CloseIcon, SettingsIcon } from "./Icons";
import { type ThemeChoice, useTheme } from "./Providers";
import { useToast } from "./Toaster";

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
type Tab = (typeof TABS)[number]["value"];

/** The settings button, and the settings window it opens over a blurred page. */
export function SettingsMenu({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button ref={button} type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}
        aria-label="Settings"
        className={compact
          ? "grid h-10 w-10 place-items-center rounded-xl text-muted transition hover:bg-sunken hover:text-ink"
          : "group flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left text-muted transition hover:bg-sunken hover:text-ink"}>
        <SettingsIcon size={compact ? 24 : 40} strokeWidth={1.5}
          className="shrink-0 transition-transform duration-500 ease-out group-hover:rotate-45" />
        {!compact && <span className="text-sm font-medium">Settings</span>}
      </button>
      {open && <SettingsDialog onClose={() => { setOpen(false); button.current?.focus(); }} />}
    </>
  );
}

function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("profile");
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [signin, setSignin] = useState<boolean | null>(null);
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
  const toast = useToast();
  const router = useRouter();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    fetch("/api/session").then((r) => r.json()).then((j) => setSignin(Boolean(j.required))).catch(() => setSignin(false));
    fetch("/api/v/me").then(async (r) => {
      if (r.ok) setMe(await r.json());
      else setMeError(r.status === 503 ? "Demo mode: no account is connected." : "Couldn't load the account.");
    }).catch(() => setMeError("Couldn't load the account."));
  }, []);

  // Modal behaviour: focus moves in, Tab stays inside, Escape closes, the page behind doesn't scroll.
  useEffect(() => {
    const el = panel.current;
    el?.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return onClose();
      if (e.key !== "Tab" || !el) return;
      const items = el.querySelectorAll<HTMLElement>("button, input, [tabindex]:not([tabindex='-1'])");
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  function saveSocials() {
    if (writeStored(SOCIAL_KEY, JSON.stringify(socials))) {
      setEdits({});
      toast({ kind: "success", title: "Socials saved" });
    } else {
      toast({ kind: "error", title: "Couldn't save", detail: "This browser is blocking local storage" });
    }
  }

  async function signOut() {
    await fetch("/api/session", { method: "DELETE" }).catch(() => null);
    router.replace("/signin");
    router.refresh();
  }

  const initials = (me?.name ?? "You").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();

  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="vt-backdrop absolute inset-0 bg-[color-mix(in_srgb,var(--vt-bg)_45%,transparent)] backdrop-blur-[6px]"
        onClick={onClose} aria-hidden />
      <div ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
        className="vt-pop relative flex max-h-[min(36rem,calc(100dvh-2rem))] w-full max-w-[30rem] flex-col overflow-hidden rounded-2xl border border-line bg-raised shadow-[var(--vt-shadow-pop)]">
        <div className="flex items-center justify-between px-5 pb-3 pt-4">
          <h2 id={titleId} className="text-base font-semibold">Settings</h2>
          <button type="button" onClick={onClose} aria-label="Close settings"
            className="grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink">
            <CloseIcon size={16} />
          </button>
        </div>

        <div role="tablist" aria-label="Settings sections" className="mx-5 grid grid-cols-3 gap-1 rounded-xl bg-sunken p-1 text-[13px] font-medium">
          {TABS.map((t, i) => (
            <button key={t.value} role="tab" type="button" aria-selected={tab === t.value} onClick={() => setTab(t.value)}
              data-autofocus={i === 0 ? true : undefined}
              className={`rounded-lg px-2 py-1.5 transition ${tab === t.value ? "bg-raised text-ink shadow-[var(--vt-shadow)]" : "text-muted hover:text-ink"}`}>
              {t.label}
            </button>
          ))}
        </div>

        <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
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
              <p className="text-xs leading-5 text-muted">
                {signin ? "Signed in with your own token." : "Using the workspace service account."}
              </p>
              {me && signin && (
                <button type="button" onClick={signOut} className="vt-btn vt-btn-quiet self-start">Sign out</button>
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
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-3">
              {THEMES.map((th) => (
                <button key={th.value} type="button" role="radio" aria-checked={choice === th.value}
                  onClick={() => setChoice(th.value)}
                  className={`flex flex-col gap-2 rounded-xl border p-2 text-left text-sm transition ${choice === th.value ? "border-accent ring-2 ring-accent/25" : "border-line hover:border-line-strong"}`}>
                  <ThemeSwatch kind={th.value} />
                  <span className="px-0.5 font-medium">{th.label}</span>
                </button>
              ))}
            </div>
          )}
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
  const light = pane("#eceef2", "#f6f7f9", "#1d6ae5");
  const dark = pane("#0c0e13", "#1a1e27", "#4c9bff");
  return (
    <span aria-hidden className="flex h-14 w-full overflow-hidden rounded-lg border border-line">
      {kind === "light" ? light : kind === "dark" ? dark : <>{light}{dark}</>}
    </span>
  );
}

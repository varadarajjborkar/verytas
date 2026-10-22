"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useStored, writeStored } from "@/lib/stored";
import { type ThemeChoice, useTheme } from "./Providers";
import { useToast } from "./Toaster";

type Me = { id: number; email: string; name: string; role: string; clearance: string };
const SOCIAL_KEY = "vt-social-profiles";
const PLATFORMS = [
  { key: "instagram", label: "Instagram", placeholder: "@yourbrand" },
  { key: "x", label: "X (Twitter)", placeholder: "@yourbrand" },
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
type Tab = "profile" | "social" | "theme";

/** Settings in the bottom-left corner: who you are, the brand's social handles, and the theme. */
export function SettingsMenu({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("profile");
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
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
  const setSocials = (fn: (s: Record<string, string>) => Record<string, string>) => setEdits((e) => fn({ ...savedSocials, ...e }));
  const { choice, setChoice } = useTheme();
  const toast = useToast();
  const router = useRouter();
  const panel = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open || me) return;
    fetch("/api/v/me").then(async (r) => {
      if (r.ok) setMe(await r.json());
      else setMeError(r.status === 503 ? "Demo mode: no account is connected." : "Couldn't load the account.");
    }).catch(() => setMeError("Couldn't load the account."));
  }, [open, me]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && (setOpen(false), button.current?.focus());
    const onClick = (e: MouseEvent) => {
      if (!panel.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  function saveSocials() {
    if (writeStored(SOCIAL_KEY, JSON.stringify(socials))) {
      setEdits({});
      toast({ kind: "success", title: "Social profiles saved", detail: "Stored in this browser" });
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
  const field = "w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink focus:border-accent focus:outline-none";

  return (
    <div className="relative">
      <button ref={button} type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-controls={id}
        aria-label="Settings"
        className={compact ? "grid h-9 w-9 place-items-center rounded-lg text-muted hover:bg-bg hover:text-ink"
          : "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm hover:bg-bg"}>
        {compact ? (
          <span aria-hidden className="text-lg leading-none">⚙</span>
        ) : (
          <>
            <span aria-hidden className="grid h-7 w-7 place-items-center rounded-full bg-accent/15 text-[11px] font-semibold text-accent">{initials}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{me?.name ?? "Settings"}</span>
              <span className="block text-xs text-muted">Profile, socials, theme</span>
            </span>
            <span aria-hidden className="text-muted">⚙</span>
          </>
        )}
      </button>

      {open && (
        <div ref={panel} id={id} role="dialog" aria-label="Settings"
          className={`vt-toast-in z-40 w-[19rem] rounded-xl border border-line bg-surface p-3 shadow-xl ${compact ? "absolute right-0 top-11" : "absolute bottom-full left-0 mb-2"}`}>
          <div role="tablist" aria-label="Settings sections" className="mb-3 grid grid-cols-3 gap-1 rounded-lg bg-bg p-1 text-xs font-medium">
            {(["profile", "social", "theme"] as Tab[]).map((t) => (
              <button key={t} role="tab" type="button" aria-selected={tab === t} onClick={() => setTab(t)}
                className={`rounded-md px-2 py-1.5 capitalize transition ${tab === t ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
                {t === "social" ? "Socials" : t}
              </button>
            ))}
          </div>

          {tab === "profile" && (
            <div className="flex flex-col gap-2 text-sm">
              {me ? (
                <dl className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-y-1.5 text-xs">
                  <dt className="text-muted">Name</dt><dd className="truncate">{me.name}</dd>
                  <dt className="text-muted">Email</dt><dd className="truncate">{me.email}</dd>
                  <dt className="text-muted">Role</dt><dd className="capitalize">{me.role.replace("_", " ")}</dd>
                  <dt className="text-muted">Clearance</dt><dd className="capitalize">{me.clearance}</dd>
                </dl>
              ) : (
                <p className="text-xs text-muted">{meError ?? "Loading…"}</p>
              )}
              <p className="border-t border-line pt-2 text-[11px] text-muted">
                You are signed in with your own token. Your role decides whether you can approve, dismiss blockers or edit rules.
              </p>
              {me && (
                <button type="button" onClick={signOut}
                  className="self-start rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-muted hover:text-ink">
                  Sign out
                </button>
              )}
            </div>
          )}

          {tab === "social" && (
            <div className="flex flex-col gap-2">
              <p className="text-[11px] text-muted">The brand&apos;s own accounts, so reviewers know where each post will go.</p>
              <div className="flex max-h-64 flex-col gap-2 overflow-auto pr-0.5">
                {PLATFORMS.map((pl) => (
                  <label key={pl.key} className="flex flex-col gap-0.5 text-[11px] font-medium text-muted">
                    {pl.label}
                    <input className={field} value={socials[pl.key] ?? ""} placeholder={pl.placeholder} maxLength={120}
                      onChange={(e) => setSocials((s) => ({ ...s, [pl.key]: e.target.value }))} />
                  </label>
                ))}
              </div>
              <button type="button" onClick={saveSocials}
                className="self-end rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-ink hover:brightness-110">Save</button>
            </div>
          )}

          {tab === "theme" && (
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2">
              {THEMES.map((th) => (
                <button key={th.value} type="button" role="radio" aria-checked={choice === th.value}
                  onClick={() => { setChoice(th.value); toast({ kind: "info", title: `Theme: ${th.label}` }); }}
                  className={`flex flex-col items-center gap-1.5 rounded-lg border p-2 text-xs transition ${choice === th.value ? "border-accent bg-accent/10 font-medium" : "border-line hover:border-accent/50"}`}>
                  <ThemeSwatch kind={th.value} />
                  {th.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ThemeSwatch({ kind }: { kind: ThemeChoice }) {
  const light = <span className="block h-full w-full bg-[#f7f8fa]"><span className="m-1 block h-1.5 w-6 rounded bg-[#4f46e5]" /></span>;
  const dark = <span className="block h-full w-full bg-[#0e1015]"><span className="m-1 block h-1.5 w-6 rounded bg-[#8f8cff]" /></span>;
  return (
    <span aria-hidden className="flex h-9 w-full overflow-hidden rounded-md border border-line">
      {kind === "light" ? light : kind === "dark" ? dark : <>{light}{dark}</>}
    </span>
  );
}

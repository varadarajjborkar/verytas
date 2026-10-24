"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { ArrowLeftIcon, InfoIcon } from "./Icons";

type Mode = "signin" | "signup";
type Side = "creator" | "company";

const field = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-accent focus:outline-none";

/**
 * Your own account: sign in with a password, or sign up as a creator (with the join code your brand team
 * gave you) or as a brand team (which makes a new, empty company). Real and working, but empty, and the
 * info note says so: everything worth seeing is in the live demo's companies, one link away.
 */
export function AccountPanel({ next, demo }: { next: string; demo: boolean }) {
  const [mode, setMode] = useState<Mode>("signin");
  const [side, setSide] = useState<Side>("creator");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [made, setMade] = useState<{ company: string; joinCode: string } | null>(null);
  const [about, setAbout] = useState(false);
  const aboutId = useId();

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const action = mode === "signin" ? "signin" : side;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/session/account", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...form }) });
      const out = await res.json().catch(() => null);
      if (!res.ok) {
        setError(out?.error ?? "That didn't work.");
        return;
      }
      // A new company's join code is shown once here before going in; it is also in the settings menu.
      if (action === "company" && out?.joinCode) {
        setMade({ company: out.company, joinCode: out.joinCode });
        return;
      }
      window.location.assign(next);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const back = demo && (
    <Link href="/signin" className="inline-flex items-center gap-1.5 self-start text-sm font-medium text-muted hover:text-accent">
      <ArrowLeftIcon size={15} />Back to the live demo
    </Link>
  );

  if (made) {
    return (
      <div className="my-auto flex w-full max-w-md flex-col gap-4 self-center">
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">{made.company} is ready</h1>
        <p className="text-sm leading-6 text-muted">
          Creators join your company with this code when they sign up. You can find it again in the settings menu.
        </p>
        <p className="select-all rounded-xl bg-sunken px-4 py-3 text-center font-mono text-xl font-semibold tracking-[0.3em]">{made.joinCode}</p>
        <button type="button" onClick={() => window.location.assign(next)}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink shadow-sm hover:brightness-110">
          Go to {made.company}
        </button>
      </div>
    );
  }

  return (
    <div className="my-auto flex w-full max-w-md flex-col gap-5 self-center">
      {back}
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">
            {mode === "signin" ? "Sign in to Verytas" : "Create your account"}
          </h1>
          <button type="button" aria-expanded={about} aria-controls={aboutId} onClick={() => setAbout((v) => !v)}
            aria-label="About accounts on this demo"
            className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line text-subtle hover:border-accent hover:text-accent">
            <InfoIcon size={13} />
          </button>
        </div>
        {about && (
          <p id={aboutId} className="rounded-xl bg-sunken px-4 py-3 text-xs leading-5 text-muted">
            Accounts work like the real product, and a company you make here starts empty: no brand library, no posts,
            only Verytas&apos;s built-in checks. Your home page then lists what to set up, and you can hand over your own
            brand material or load a sample brand kit to try a review straight away. Creators join with the code
            shown in your settings.{demo
              ? " To see Verytas at work, go back to the live demo and pick a person at one of its companies."
              : ""} Accounts made here are removed when the demo resets.
          </p>
        )}
      </header>

      <div role="tablist" aria-label="Sign in or sign up" className="grid grid-cols-2 gap-1 rounded-xl bg-sunken p-1 text-sm">
        {(["signin", "signup"] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setError(null); }}
            className={`rounded-lg px-3 py-1.5 font-medium ${mode === m ? "bg-raised text-ink shadow-sm" : "text-muted hover:text-ink"}`}>
            {m === "signin" ? "Sign in" : "Sign up"}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-3">
        {mode === "signup" && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">I am</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {([["creator", "A creator", "I write posts for a brand"], ["company", "A brand team", "I manage a brand's content"]] as const).map(([v, label, hint]) => (
                <label key={v} className={`flex cursor-pointer flex-col rounded-xl border p-3 text-sm ${side === v ? "border-accent bg-accent/8" : "border-line hover:border-accent/50"}`}>
                  <span className="flex items-center gap-2 font-medium">
                    <input type="radio" name="side" value={v} checked={side === v} onChange={() => setSide(v)} className="accent-[var(--vt-accent)]" />
                    {label}
                  </span>
                  <span className="mt-0.5 pl-5 text-xs text-subtle">{hint}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {mode === "signup" && side === "company" && (
          <label className="flex flex-col gap-1 text-sm font-medium">Company name
            <input name="company_name" required minLength={2} maxLength={120} autoComplete="organization" className={field} />
            <span className="text-xs font-normal text-subtle">A new, empty company is made, with you as its head of brand.</span>
          </label>
        )}
        {mode === "signup" && side === "creator" && (
          <label className="flex flex-col gap-1 text-sm font-medium">Join code
            <input name="join_code" required pattern="[A-Za-z0-9]{6,16}" autoCapitalize="characters" spellCheck={false}
              className={`${field} font-mono uppercase tracking-widest`} />
            <span className="text-xs font-normal text-subtle">Your brand team finds it in their settings menu.</span>
          </label>
        )}
        {mode === "signup" && (
          <label className="flex flex-col gap-1 text-sm font-medium">Your name
            <input name="name" required maxLength={200} autoComplete="name" className={field} />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm font-medium">Email
          <input name="email" type="email" required maxLength={320} autoComplete="email" className={field} />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">Password
          <input name="password" type="password" required minLength={mode === "signup" ? 10 : 1} maxLength={128}
            autoComplete={mode === "signup" ? "new-password" : "current-password"} className={field} />
          {mode === "signup" && <span className="text-xs font-normal text-subtle">At least 10 characters.</span>}
        </label>
        {error && <p role="alert" className="rounded-lg bg-[var(--vt-blocker-bg)] px-3 py-2 text-sm text-[var(--vt-blocker)]">{error}</p>}
        <button type="submit" disabled={busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink shadow-sm transition hover:brightness-110 disabled:opacity-50">
          {busy ? "One moment…" : mode === "signin" ? "Sign in" : side === "company" ? "Create the company" : "Join and sign in"}
        </button>
      </form>
    </div>
  );
}

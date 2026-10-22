"use client";

import { useState } from "react";
import { ArrowRightIcon, CalendarIcon, InfoIcon, RefreshIcon, UsersIcon } from "./Icons";
import { SignInShell } from "./SignInShell";

type Person = { key: string; name: string; side: "manager" | "creator"; title: string; blurb: string };

const SIDES = [
  { side: "manager" as const, label: "Brand team", lead: "Decide on what creators send, keep the brand library, read the dashboards." },
  { side: "creator" as const, label: "Creators", lead: "Write a post, see what Verytas flags and why, fix it and send it for approval." },
];

/**
 * The shared demo's front door: pick a person, and you are signed in as that real account. Come back
 * here (Switch account, in the sidebar) to be someone else; everything done as each person stays.
 */
export function DemoSignIn({ brand, resetsOn, people, next }: { brand: string; resetsOn: string; people: Person[]; next: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function enter(key: string) {
    setBusy(key);
    setError(null);
    try {
      const res = await fetch("/api/session/demo", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }) });
      if (!res.ok) {
        setError((await res.json().catch(() => null))?.error ?? "Couldn't sign in.");
        setBusy(null);
        return;
      }
      // A full navigation, so every server page renders as the new person.
      window.location.assign(next);
    } catch {
      setError("Couldn't reach the server.");
      setBusy(null);
    }
  }

  // One locale and zone on server and browser alike, or the date renders twice differently and hydration fails.
  const reset = new Date(`${resetsOn}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
  return (
    <SignInShell>
      <header className="flex flex-col gap-2">
        <p className="text-xs font-semibold uppercase tracking-[0.08em] text-accent">Live demo</p>
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight">Pick someone at {brand} to be</h1>
        <p className="max-w-xl text-sm leading-6 text-muted">
          {brand} is a made-up online learning brand with three weeks of work already in it. Each person below is a
          real account with their own role, so you see exactly what they would.
        </p>
      </header>

      {SIDES.map(({ side, label, lead }) => (
        <section key={side} aria-labelledby={`side-${side}`} className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id={`side-${side}`} className="text-sm font-semibold">{label}</h2>
            <p className="hidden text-xs text-subtle sm:block">{lead}</p>
          </div>
          <ul className="vt-stagger grid gap-2.5 sm:grid-cols-2">
            {people.filter((p) => p.side === side).map((p) => (
              <li key={p.key}>
                <button type="button" onClick={() => enter(p.key)} disabled={busy !== null}
                  className="vt-lift group flex h-full w-full items-start gap-3 rounded-[14px] border border-line bg-raised p-4 text-left shadow-[var(--vt-shadow)] hover:border-accent/60 disabled:opacity-60">
                  <span aria-hidden className={`grid h-10 w-10 shrink-0 place-items-center rounded-full text-xs font-semibold ${
                    side === "manager" ? "bg-accent/12 text-accent" : "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]"}`}>
                    {p.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{p.name}</span>
                    <span className="block truncate text-xs text-subtle">{p.title}</span>
                    <span className="mt-1.5 block text-xs leading-5 text-muted">{p.blurb}</span>
                  </span>
                  {busy === p.key ? (
                    <span role="img" aria-label="Signing in" className="mt-1 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                  ) : (
                    <ArrowRightIcon size={16} className="mt-1 shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-accent" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {error && <p role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}

      <section aria-labelledby="demo-notes" className="mt-auto rounded-2xl bg-sunken/70 p-4">
        <h2 id="demo-notes" className="mb-3 text-xs font-semibold uppercase tracking-[0.08em] text-subtle">Good to know</h2>
        <ul className="grid gap-3 text-xs leading-5 text-muted sm:grid-cols-2">
          <li className="flex gap-2.5"><UsersIcon size={15} className="mt-0.5 shrink-0 text-subtle" />
            <span>One shared demo: what you add or change is saved, and other visitors see it too.</span></li>
          <li className="flex gap-2.5"><RefreshIcon size={15} className="mt-0.5 shrink-0 text-subtle" />
            <span>Be someone else any time with <span className="font-medium text-ink">Switch account</span> in the sidebar. Your work stays.</span></li>
          <li className="flex gap-2.5"><CalendarIcon size={15} className="mt-0.5 shrink-0 text-subtle" />
            <span>Everything resets every 14 days. Next reset: <span className="font-medium text-ink">{reset}</span>.</span></li>
          <li className="flex gap-2.5"><InfoIcon size={15} className="mt-0.5 shrink-0 text-subtle" />
            <span>Please upload nothing private. Confidential terms are redacted before any AI call.</span></li>
        </ul>
      </section>
    </SignInShell>
  );
}

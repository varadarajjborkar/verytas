"use client";

import { useState } from "react";
import Link from "next/link";
import { useStored, writeStored } from "@/lib/stored";
import { ArrowRightIcon, InfoIcon, RefreshIcon, UsersIcon } from "./Icons";
import { SignInShell } from "./SignInShell";

type Person = { key: string; name: string; side: "manager" | "creator"; title: string; blurb: string };
type Company = { slug: string; brand: string; industry: string; people: Person[] };

const PICKED = "vt_demo_company";

const SIDES = [
  { side: "manager" as const, label: "Brand team", lead: "Review what creators send, and approve it" },
  { side: "creator" as const, label: "Creators", lead: "Write a post, see what to fix, and send it" },
];

/**
 * The shared demo's front door: pick a company, then a person, and you are signed in as that real account.
 * Come back here (Switch account, in the sidebar) to be someone else, or someone at another company;
 * everything done as each person stays. Where the server takes sign-ups, a link at the top leads to a
 * separate page for an account of your own, so the two never share a screen.
 */
export function DemoSignIn({ companies, resetsOn, next, selfSignup }:
  { companies: Company[]; resetsOn: string; next: string; selfSignup: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const picked = useStored(PICKED);
  const company = companies.find((c) => c.slug === picked) ?? companies[0];
  const { brand, people } = company;

  async function enter(key: string) {
    setBusy(key);
    setError(null);
    try {
      const res = await fetch("/api/session/demo", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, company: company.slug }) });
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
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.08em] text-accent">Live demo</p>
          {selfSignup && (
            <Link href={next === "/" ? "/signin/account" : `/signin/account?next=${encodeURIComponent(next)}`}
              className="rounded-lg border border-line px-3 py-1.5 text-xs font-semibold text-muted hover:border-accent hover:text-accent">
              Sign in or sign up
            </Link>
          )}
        </div>
        <h1 className="text-[1.75rem] font-semibold leading-tight tracking-tight [@media(min-width:768px)_and_(max-height:800px)]:text-2xl">Pick someone at {brand} to be</h1>
        <p className="max-w-xl text-sm leading-6 text-muted [@media(min-width:768px)_and_(max-height:800px)]:leading-5">
          A made-up brand with eight weeks of work already in it. Each person is a real account, so you see
          exactly what they would.
        </p>
      </header>

      {companies.length > 1 && (
        <section aria-labelledby="pick-company" className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="pick-company" className="text-sm font-semibold">Company</h2>
          </div>
          <div role="radiogroup" aria-labelledby="pick-company" className="flex flex-wrap gap-2">
            {companies.map((c) => (
              <button key={c.slug} type="button" role="radio" aria-checked={c.slug === company.slug}
                onClick={() => writeStored(PICKED, c.slug)} disabled={busy !== null}
                className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition ${c.slug === company.slug
                  ? "border-accent bg-accent text-accent-ink shadow-sm" : "border-line text-muted hover:border-accent/60 hover:text-ink"}`}>
                {c.brand}
              </button>
            ))}
          </div>
        </section>
      )}

      {SIDES.map(({ side, label, lead }) => (
        <section key={side} aria-labelledby={`side-${side}`} className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id={`side-${side}`} className="text-sm font-semibold">{label}</h2>
            <p className="text-xs text-subtle">{lead}</p>
          </div>
          <ul className="vt-stagger grid gap-2.5 sm:grid-cols-2">
            {people.filter((p) => p.side === side).map((p) => (
              <li key={p.key}>
                {/* Name, job and what they do: enough to choose by, short enough to scan. */}
                <button type="button" onClick={() => enter(p.key)} disabled={busy !== null} title={p.blurb}
                  className="vt-lift group flex h-full w-full items-start gap-3 rounded-[14px] border border-line bg-raised p-3.5 text-left shadow-[var(--vt-shadow)] hover:border-accent/60 disabled:opacity-60 [@media(min-width:768px)_and_(max-height:800px)]:p-2.5">
                  <span aria-hidden className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-semibold ${
                    side === "manager" ? "bg-accent/12 text-accent" : "bg-[var(--vt-ok-bg)] text-[var(--vt-ok)]"}`}>
                    {p.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{p.name}</span>
                    <span className="block truncate text-xs text-subtle">{p.title}</span>
                    {/* What they do, in two lines at most; the whole description is on hover. */}
                    <span className="mt-1 line-clamp-2 text-xs leading-[1.125rem] text-muted">{p.blurb}</span>
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
          {/* The picker offers a few people to sign in as; the company has more, and their work shows up too. */}
          {side === "creator" && (
            <p className="text-xs text-subtle">
              {brand} works with more creators than these. Signed in on the brand team, you will see all of
              them in the review queue, escalations and Creators; a creator sees only their own work.
            </p>
          )}
        </section>
      ))}

      {error && <p role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}

      <ul aria-label="Good to know" className="mt-3 flex flex-col gap-1.5 [@media(min-width:768px)_and_(max-height:800px)]:mt-0 [@media(min-width:768px)_and_(max-height:800px)]:gap-1 text-xs text-muted">
        <li className="flex items-center gap-2"><UsersIcon size={14} className="shrink-0 text-subtle" />
          Everyone is made up, and the demo is shared with other visitors.</li>
        <li className="flex items-center gap-2"><RefreshIcon size={14} className="shrink-0 text-subtle" />
          Switch account any time from the sidebar. Resets on {reset}.</li>
        <li className="flex items-center gap-2"><InfoIcon size={14} className="shrink-0 text-subtle" />
          Please don&apos;t upload anything private.</li>
      </ul>
    </SignInShell>
  );
}

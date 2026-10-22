"use client";

import { useState } from "react";
import { ArrowRightIcon } from "./Icons";

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
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 py-4 md:py-10">
      <header className="vt-stagger flex flex-col gap-3">
        <span aria-hidden className="vt-mark grid h-10 w-10 place-items-center rounded-xl text-base font-bold">V</span>
        <h1 className="text-[1.9rem] font-semibold leading-tight tracking-tight">Try Verytas as someone at {brand}</h1>
        <p className="max-w-2xl text-sm leading-6 text-muted">
          Verytas checks content before it is published: claims against approved facts, the brand&apos;s words and
          voice, artwork, accessibility and confidential terms. Every issue says why and cites its source, and people
          make the final call. {brand} is a made-up online learning brand with three weeks of work already in it.
        </p>
      </header>

      {SIDES.map(({ side, label, lead }) => (
        <section key={side} aria-labelledby={`side-${side}`} className="flex flex-col gap-3">
          <div>
            <h2 id={`side-${side}`} className="text-sm font-semibold">{label}</h2>
            <p className="text-xs text-muted">{lead}</p>
          </div>
          <ul className="vt-stagger grid gap-2.5 sm:grid-cols-2">
            {people.filter((p) => p.side === side).map((p) => (
              <li key={p.key}>
                <button type="button" onClick={() => enter(p.key)} disabled={busy !== null}
                  className="vt-card vt-lift group flex h-full w-full items-start gap-3 p-4 text-left disabled:opacity-60">
                  <span aria-hidden className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sunken text-xs font-semibold text-muted">
                    {p.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">{p.name}</span>
                      <span className="truncate text-xs text-subtle">{p.title}</span>
                    </span>
                    <span className="mt-1 block text-xs leading-5 text-muted">{p.blurb}</span>
                  </span>
                  {busy === p.key ? (
                    <span role="img" aria-label="Signing in" className="mt-1 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-accent border-t-transparent" />
                  ) : (
                    <ArrowRightIcon size={15} className="mt-1 shrink-0 text-subtle transition group-hover:translate-x-0.5 group-hover:text-accent" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {error && <p role="alert" className="rounded-xl bg-[var(--vt-blocker-bg)] px-4 py-3 text-sm text-[var(--vt-blocker)]">{error}</p>}

      <section aria-labelledby="demo-notes" className="border-l-2 border-accent/50 pl-4 text-xs leading-5 text-muted">
        <h2 id="demo-notes" className="mb-1.5 text-sm font-semibold text-ink">Before you start</h2>
        <ul className="flex list-disc flex-col gap-1 pl-4 marker:text-subtle">
          <li>This is one shared demo. What you add or change (posts, decisions, rules) is saved and other visitors see it too.</li>
          <li>Switch to another person at any time with <span className="font-medium text-ink">Switch account</span> at the bottom of the sidebar. Your work stays where you left it.</li>
          <li>All data is reset to the starting state every 14 days. The next reset is on <span className="font-medium text-ink">{reset}</span>, so anything you add disappears then.</li>
          <li>Please don&apos;t upload anything private. Text and images are checked on this server; model calls go to an AI service after confidential terms are redacted.</li>
        </ul>
      </section>
    </div>
  );
}

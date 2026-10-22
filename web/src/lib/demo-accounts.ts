import "server-only";

import { readFileSync } from "node:fs";

// The shared demo's sign-in: instead of pasting a token, a visitor picks one of the seeded people and is
// signed in as that real account (roles and clearances apply as for anyone). The tokens live in a
// server-side file written by `verytas.cli seed-showcase --write-demo-accounts`; only names, titles
// and sides ever reach the browser. Off unless VERYTAS_DEMO_ACCOUNTS points at that file.

export type DemoPerson = { key: string; name: string; side: "manager" | "creator"; title: string; blurb: string };
type DemoFile = { brand: string; seeded_at: string; people: (DemoPerson & { token: string })[] };

/** How long the shared data lives before it is reseeded; the sign-in page says so. */
export const RESET_DAYS = 14;

function load(): DemoFile | null {
  const path = process.env.VERYTAS_DEMO_ACCOUNTS;
  if (!path) return null;
  try {
    // Read on every call: the reset job rewrites the file with fresh tokens, and the server keeps running.
    return JSON.parse(readFileSync(path, "utf8")) as DemoFile;
  } catch {
    return null;
  }
}

export function demoAccounts(): { brand: string; resetsOn: string; people: DemoPerson[] } | null {
  const f = load();
  if (!f?.people?.length) return null;
  const resetsOn = new Date(new Date(f.seeded_at).getTime() + RESET_DAYS * 86_400_000).toISOString().slice(0, 10);
  return { brand: f.brand, resetsOn, people: f.people.map(({ key, name, side, title, blurb }) => ({ key, name, side, title, blurb })) };
}

export function demoToken(key: string): string | null {
  return load()?.people.find((p) => p.key === key)?.token ?? null;
}

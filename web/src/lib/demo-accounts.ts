import "server-only";

import { readFileSync } from "node:fs";

// The shared demo's sign-in: instead of pasting a token, a visitor picks one of the seeded people and is
// signed in as that real account (roles and clearances apply as for anyone). The tokens live in a
// server-side file written by `verytas.cli seed-showcase --write-demo-accounts`; only names, titles
// and sides ever reach the browser. Off unless VERYTAS_DEMO_ACCOUNTS points at that file.

export type DemoPerson = { key: string; name: string; side: "manager" | "creator"; title: string; blurb: string };
export type DemoCompany = { slug: string; brand: string; industry: string; people: DemoPerson[] };
type Stored = DemoPerson & { token: string };
type DemoFile = {
  brand: string;
  seeded_at: string;
  people: Stored[];
  // Every seeded company; files from before there were several have only the top-level brand.
  companies?: { brand: string; industry: string; people: Stored[] }[];
};

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

const slugOf = (brand: string) => brand.toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 20) || "demo";

function companies(f: DemoFile): { slug: string; brand: string; industry: string; people: Stored[] }[] {
  const list = f.companies?.length ? f.companies : [{ brand: f.brand, industry: "", people: f.people }];
  return list.filter((c) => c.people?.length).map((c) => ({ ...c, slug: slugOf(c.brand) }));
}

export function demoAccounts(): { resetsOn: string; companies: DemoCompany[] } | null {
  const f = load();
  const list = f ? companies(f) : [];
  if (!f || !list.length) return null;
  const resetsOn = new Date(new Date(f.seeded_at).getTime() + RESET_DAYS * 86_400_000).toISOString().slice(0, 10);
  return {
    resetsOn,
    companies: list.map(({ slug, brand, industry, people }) => ({
      slug, brand, industry,
      people: people.map(({ key, name, side, title, blurb }) => ({ key, name, side, title, blurb })),
    })),
  };
}

/** The token for one person at one company. Keys repeat across companies ("admin"), so both are needed;
 * without a company, the first one's (what a page from before several companies would send). */
export function demoToken(key: string, company?: string): string | null {
  const f = load();
  if (!f) return null;
  const list = companies(f);
  const co = company ? list.find((c) => c.slug === company) : list[0];
  return co?.people.find((p) => p.key === key)?.token ?? null;
}

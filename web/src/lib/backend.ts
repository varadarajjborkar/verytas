import "server-only";

import { demoBody, demoHealth, demoOverview, demoRecurring, demoReview } from "./demo-data";
import type { Overview, Recurring, Review, ReviewResult, RuleHealth, Sourced } from "./types";

// The browser never talks to the API directly: these helpers run on the server
// with a service token, so the token never reaches client bundles.
const API_URL = process.env.VERYTAS_API_URL;
const API_TOKEN = process.env.VERYTAS_API_TOKEN;

export const backendConfigured = Boolean(API_URL && API_TOKEN);

class BackendError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
      ...init.headers,
    },
    cache: "no-store",
    signal: init.signal ?? AbortSignal.timeout(90_000),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new BackendError(res.status, `${init.method ?? "GET"} ${path} -> ${res.status} ${detail.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

/** Live data when the backend is configured and reachable, otherwise labelled demo data. */
async function liveOrDemo<T>(path: string, demo: T): Promise<Sourced<T>> {
  if (!backendConfigured) return { data: demo, source: "demo" };
  try {
    return { data: await call<T>(path), source: "live" };
  } catch (err) {
    console.error("[verytas] falling back to demo data:", (err as Error).message);
    return { data: demo, source: "demo" };
  }
}

export const getOverview = () => liveOrDemo<Overview>("/insights/overview", demoOverview);
export const getGuidelineHealth = () => liveOrDemo<RuleHealth[]>("/insights/guideline-health", demoHealth);
export const getRecurring = () => liveOrDemo<Recurring[]>("/insights/recurring", demoRecurring);

type SubmitOut = { content: { id: number }; version: { id: number; body: string }; review_id: number };

export async function submitForReview(input: { title: string; channel: string; body: string }): Promise<ReviewResult> {
  if (!backendConfigured) {
    return { review: demoReview, body: demoBody, source: "demo" };
  }
  const submitted = await call<SubmitOut>("/contents?wait=true", {
    method: "POST",
    body: JSON.stringify({ title: input.title, channel: input.channel, body: input.body }),
  });
  const review = await call<Review>(`/reviews/${submitted.review_id}`);
  return { review, body: submitted.version.body, source: "live" };
}

export async function recordDecision(findingId: number, body: Record<string, unknown>): Promise<unknown> {
  if (!backendConfigured) return { demo: true };
  return call(`/findings/${findingId}/decision`, { method: "POST", body: JSON.stringify(body) });
}

export { BackendError };

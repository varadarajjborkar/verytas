import "server-only";

import { demoBody, demoHealth, demoOverview, demoRecurring, demoReview } from "./demo-data";
import { sessionToken } from "./session";
import type { Overview, Recurring, Review, ReviewResult, RuleHealth, Sourced } from "./types";

// The browser never talks to the API directly: these helpers run on the server
// as the signed-in person (lib/session.ts), whose token never reaches page scripts.
const API_URL = process.env.VERYTAS_API_URL;

export const backendConfigured = Boolean(API_URL);

class BackendError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await sessionToken();
  if (!token) throw new BackendError(401, `${path}: not signed in`);
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
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

/** What Ask Verytas may see for this person and question; null when the API isn't reachable. */
export async function getAssistantContext(question: string): Promise<Record<string, unknown> | null> {
  if (!backendConfigured) return null;
  try {
    return await call<Record<string, unknown>>(`/assistant/context?q=${encodeURIComponent(question.slice(0, 2000))}`);
  } catch (err) {
    console.error("[verytas] assistant context unavailable:", (err as Error).message);
    return null;
  }
}

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

/** Raw pass-through for the browser proxy (app/api/v). Status and body are relayed unchanged. */
export async function forward(method: string, path: string, body: ReadableStream<Uint8Array> | undefined,
  contentType: string | null, token: string): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method,
    body,
    // Streamed through rather than buffered: an upload can be 150 MB.
    ...(body ? { duplex: "half" } : {}),
    headers: { Authorization: `Bearer ${token}`, ...(contentType ? { "Content-Type": contentType } : {}) },
    cache: "no-store",
    // Reviews with video or many pages take a while; the client polls rather than waiting here.
    signal: AbortSignal.timeout(180_000),
  });
}

export { BackendError };

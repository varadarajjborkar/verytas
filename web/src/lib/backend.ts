import "server-only";

import { demoBody, demoHealth, demoOverview, demoRecurring, demoReview } from "./demo-data";
import { sessionToken } from "./session";
import type { Me, Overview, Recurring, Review, ReviewResult, RuleHealth, Sourced } from "./types";

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

/** Who is looking: the signed-in person or the account their view uses. Null in demo mode or when the
 * API can't be reached, so pages can fall back to the brand-team view of the demo data. */
export async function getViewer(): Promise<Me | null> {
  if (!backendConfigured) return null;
  try {
    return await call<Me>("/me");
  } catch {
    return null;
  }
}

/** What Inki may see for this person, plus their conversation redacted with the same
 * placeholders. Null when the API isn't reachable. */
export async function getAssistantContext(messages: string[]): Promise<{ context: Record<string, unknown>; messages: string[] } | null> {
  if (!backendConfigured) return null;
  try {
    const out = await call<Record<string, unknown> & { messages: string[] }>("/assistant/context", {
      method: "POST",
      body: JSON.stringify({ messages }),
    });
    const { messages: redacted, ...context } = out;
    if (!Array.isArray(redacted) || redacted.length !== messages.length) throw new Error("conversation not returned");
    return { context, messages: redacted };
  } catch (err) {
    console.error("[verytas] assistant context unavailable:", (err as Error).message);
    return null;
  }
}

export type ItemContextResult =
  | { ok: true; context: Record<string, unknown>; messages: string[] }
  | { ok: false; status: number };

/** The redacted dossier of one piece or escalation for the Summarize panel, plus the conversation redacted
 * with it. Server-side only: it is deliberately not on the browser proxy's allowlist, so the only way to
 * reach it is through /api/assist, which never returns the dossier itself. The status is kept so the route
 * can say "not for your role" apart from "not found" and "can't reach the API". */
export async function getItemContext(kind: "content" | "escalation", id: number, messages: string[]): Promise<ItemContextResult> {
  if (!backendConfigured) return { ok: false, status: 503 };
  try {
    const out = await call<Record<string, unknown> & { messages: string[] }>("/assist/item-context", {
      method: "POST",
      body: JSON.stringify({ kind, id, messages }),
    });
    const { messages: redacted, ...context } = out;
    if (!Array.isArray(redacted) || redacted.length !== messages.length) throw new Error("conversation not returned");
    return { ok: true, context, messages: redacted };
  } catch (err) {
    console.error("[verytas] item context unavailable:", (err as Error).message);
    return { ok: false, status: err instanceof BackendError ? err.status : 503 };
  }
}

type SubmitOut ={ content: { id: number }; version: { id: number; body: string }; review_id: number };

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
  contentType: string | null, token: string, range: string | null = null): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method,
    body,
    // Streamed through rather than buffered: an upload can be 150 MB.
    ...(body ? { duplex: "half" } : {}),
    headers: { Authorization: `Bearer ${token}`, ...(contentType ? { "Content-Type": contentType } : {}),
      ...(range && /^bytes=\d*-\d*$/.test(range) ? { Range: range } : {}) },
    cache: "no-store",
    // Reviews with video or many pages take a while; the client polls rather than waiting here.
    signal: AbortSignal.timeout(180_000),
  });
}

export { BackendError };

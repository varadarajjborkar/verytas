"use client";

// One live connection per tab for "something changed" news: the conversations stream the API already keeps
// per person (api/messages.py), shared by every badge and screen that wants it. Events say only what changed
// and where (services/notify.py); whoever hears one asks the API again, so the stream never decides what
// anyone may read. Polling stays as the fallback, so a dropped stream only means the old wait.

export type LiveEvent =
  | { type: "escalations"; content_id: number }
  | { type: "review"; content_id: number }
  | { type: "message" | "read" | "inki"; conversation_id?: number }
  | { type: "ready" }
  /** The stream dropped; the browser or this module is reconnecting. */
  | { type: "down" };

type Listener = (e: LiveEvent) => void;

const listeners = new Set<Listener>();
let source: EventSource | null = null;
let retry: ReturnType<typeof setTimeout> | undefined;
// A stream refused outright (signed out, API down) is retried less and less often, up to a minute apart.
let backoff = 5_000;
// Whether the stream is up now, so a screen that starts listening late still hears "ready" and loads.
let up = false;

function connect() {
  if (source || typeof EventSource === "undefined") return;
  source = new EventSource("/api/v/conversations/stream");
  source.addEventListener("ready", () => {
    backoff = 5_000;
    up = true;
    listeners.forEach((l) => l({ type: "ready" }));
  });
  source.onmessage = (ev) => {
    let e: LiveEvent;
    try { e = JSON.parse(ev.data); } catch { return; }
    listeners.forEach((l) => l(e));
  };
  source.onerror = () => {
    up = false;
    listeners.forEach((l) => l({ type: "down" }));
    // The browser retries a dropped stream by itself; one it gave up on (signed out, API down) is retried here.
    if (source?.readyState === EventSource.CLOSED) {
      source = null;
      clearTimeout(retry);
      if (listeners.size) retry = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 60_000);
    }
  };
}

/** Hear live events until the returned function is called. The stream opens with the first listener and
 * closes with the last. */
export function onLive(listener: Listener): () => void {
  listeners.add(listener);
  connect();
  if (up) queueMicrotask(() => { if (listeners.has(listener)) listener({ type: "ready" }); });
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      clearTimeout(retry);
      source?.close();
      source = null;
      up = false;
    }
  };
}

/** Fired in this tab when a creator opens one of their pieces, so the "My reviews" badge counts again. */
export const REVIEWS_SEEN_EVENT = "vt:reviews-seen";

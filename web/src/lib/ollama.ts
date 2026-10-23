import "server-only";

// Ollama Cloud for the routes that stream straight to the browser (Ask Verytas, Summarize). A second
// account's key, when set, takes over if the first is refused or out of quota, so a long day of development
// can't leave the live demo without answers. The API side does the same (providers/ollama.py).
const KEYS = [process.env.OLLAMA_API_KEY, process.env.OLLAMA_API_KEY_FALLBACK].filter((k): k is string => Boolean(k));
const REFUSED = new Set([401, 402, 403, 429]);
const HOLD_MS = 10 * 60_000;
let backupUntil = 0;

export const ollamaConfigured = KEYS.length > 0;

/** POST to Ollama with the first key that is not refused. `body` is a string so it can be sent twice. */
export async function ollamaPost(url: string, body: string, signal?: AbortSignal): Promise<Response> {
  const start = KEYS.length > 1 && Date.now() < backupUntil ? 1 : 0;
  let res: Response | null = null;
  for (let i = start; i < KEYS.length; i++) {
    res = await fetch(url, {
      method: "POST", body, signal,
      headers: { Authorization: `Bearer ${KEYS[i]}`, "Content-Type": "application/json" },
    });
    if (!REFUSED.has(res.status) || i === KEYS.length - 1) return res;
    await res.body?.cancel().catch(() => {});
    backupUntil = Date.now() + HOLD_MS;
  }
  return res!;
}

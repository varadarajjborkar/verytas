// What a person may be shown when something fails. Messages Verytas wrote for people (the API's own `detail`,
// the console's own `error`) are shown as they are; anything else (a gateway's HTML error page, a parser's
// "Unexpected token '<'", a browser's "Failed to fetch", an upstream service's error text) is replaced with a
// plain sentence, and the original stays in the logs where an operator can read it. Safe to import anywhere.

export const NETWORK_MESSAGE = "Couldn't reach Verytas. Check the connection and try again.";
export const GENERIC_MESSAGE = "Something went wrong on our side. Try again in a moment.";
const BUSY_MESSAGE = "Verytas is busy or restarting. Try again in a moment.";
const SLOW_MESSAGE = "That took too long. Try again in a moment.";

// Markup, code, parser and runtime wording, and gateway pages: none of it was written for a reader. Kept narrow
// enough that our own sentences ("can't be null", "upload a JSON file", "at Bengaluru (HQ)") still get through.
const INTERNAL = new RegExp([
  String.raw`<\s*[a-z!/]`, String.raw`JSON\.parse|in JSON at position|is not valid JSON`, "Unexpected (token|end)",
  "Failed to fetch", "NetworkError", "Load failed", "did not match the expected pattern", "Cannot read",
  "is not a function", String.raw`\b(?:null|undefined) is not\b`, String.raw`of (?:null|undefined)\b`, "Traceback",
  "stack trace", "ECONN", "ETIMEDOUT", "fetch failed", "Internal Server Error", "Bad Gateway",
  "Gateway Time-?out", "Service Unavailable", "cloudflare", "nginx", "upstream", String.raw`\bHTTP/\d`,
  String.raw`->\s*\d{3}\b`, String.raw`^\w+: \d{3}$`,
].join("|"), "i");
// Case matters for these: a class name like "TypeError" or "KeyError", and a stack frame's "at fn (file:1:2)".
const CODE = new RegExp([
  String.raw`\b[A-Z]\w*(?:Exception|Error)\b`, String.raw`^(?:Error|Exception)\b`, String.raw`\bat \S+ \([^)]*:\d+:\d+\)`,
].join("|"));
const MAX_SHOWN = 400;

/** True when `message` reads as something written for a person rather than leaked from the machinery. */
export function isSafeMessage(message: unknown): message is string {
  return typeof message === "string" && message.trim().length > 0 && message.length <= MAX_SHOWN
    && !INTERNAL.test(message) && !CODE.test(message);
}

/** A plain sentence for an HTTP status when the response's own words can't be shown. */
export function statusMessage(status: number): string {
  if (status === 0) return NETWORK_MESSAGE;
  if (status === 401) return "Your session has expired. Sign in again.";
  if (status === 403) return "You don't have access to that.";
  if (status === 404) return "That isn't available any more.";
  if (status === 408 || status === 504 || status === 524) return SLOW_MESSAGE;
  if (status === 413) return "That is too large to send.";
  if (status === 429) return "Too many requests just now. Wait a moment and try again.";
  if (status === 502 || status === 503 || (status >= 520 && status <= 530)) return BUSY_MESSAGE;
  if (status >= 500) return GENERIC_MESSAGE;
  return "That couldn't be done. Check it and try again.";
}

/** The text to show for a caught error: its own message when that is safe, otherwise `fallback`. */
export function shownError(err: unknown, fallback: string = GENERIC_MESSAGE): string {
  if (err instanceof TypeError) return NETWORK_MESSAGE; // fetch's own failure: offline, DNS, refused, CORS
  const name = (err as { name?: unknown })?.name;
  if (name === "TimeoutError") return SLOW_MESSAGE;
  const message = (err as { message?: unknown })?.message;
  return isSafeMessage(message) ? message : fallback;
}

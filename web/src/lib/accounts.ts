import "server-only";

/** Whether the API takes sign-ups and password sign-in; asked per request, and "no" when it can't be reached. */
export async function selfSignup(): Promise<boolean> {
  const api = process.env.VERYTAS_API_URL;
  if (!api) return false;
  const res = await fetch(`${api}/accounts/config`, { cache: "no-store", signal: AbortSignal.timeout(3_000) }).catch(() => null);
  return Boolean(res?.ok && (await res.json().catch(() => null))?.self_signup);
}

/** Only same-site paths, so a sign-in link can't bounce people elsewhere. Browsers read "/\evil.com" as
 * "//evil.com" and drop tabs and newlines, so those are refused with the "//" form. */
export function safeNext(asked: unknown): string {
  return typeof asked === "string" && /^\/(?![/\\])/.test(asked) && !/[\\\s\u0000-\u001f]/.test(asked) ? asked : "/";
}

import { cookies } from "next/headers";
import { z } from "zod/v4";
import { demoToken } from "@/lib/demo-accounts";
import { SESSION_COOKIE, cookieOptions } from "@/lib/session";

const API_URL = process.env.VERYTAS_API_URL;
const Input = z.object({ key: z.string().regex(/^[a-z0-9]{1,20}$/) });

/** Sign in as one of the demo's people. Same-site JSON only, like the token sign-in. */
export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if ((origin && new URL(origin).host !== new URL(request.url).host)
    || !(request.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "Sign in from this console." }, { status: 403 });
  }
  const parsed = Input.safeParse(await request.json().catch(() => null));
  const token = parsed.success ? demoToken(parsed.data.key) : null;
  if (!API_URL || !token) return Response.json({ error: "That demo account isn't available." }, { status: 404 });
  // Checked against the API first: after a reset the file has new tokens, and a stale one must not stick.
  const res = await fetch(`${API_URL}/me`, { headers: { Authorization: `Bearer ${token}` }, cache: "no-store",
    signal: AbortSignal.timeout(10_000) }).catch(() => null);
  if (!res?.ok) return Response.json({ error: "The demo is being reset. Try again in a minute." }, { status: 503 });
  (await cookies()).set(SESSION_COOKIE, token, cookieOptions());
  return Response.json(await res.json());
}

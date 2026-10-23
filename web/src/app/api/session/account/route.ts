import { cookies } from "next/headers";
import { z } from "zod/v4";
import { SESSION_COOKIE, cookieOptions } from "@/lib/session";
import { crossOrigin } from "@/lib/same-origin";

const API_URL = process.env.VERYTAS_API_URL;

const Email = z.email().max(320);
const Password = z.string().min(10).max(128);
const Name = z.string().trim().min(1).max(200);
const Input = z.discriminatedUnion("action", [
  z.object({ action: z.literal("signin"), email: Email, password: z.string().min(1).max(128) }),
  z.object({ action: z.literal("company"), email: Email, password: Password, name: Name,
    company_name: z.string().trim().min(2).max(120) }),
  z.object({ action: z.literal("creator"), email: Email, password: Password, name: Name,
    join_code: z.string().trim().regex(/^[A-Za-z0-9]{6,16}$/) }),
]);

// Attempts per address per 10 minutes. The API has its own limits (sign-ups per hour, wrong passwords
// per email); this keeps one visitor from spending all of them. In memory: one web server serves the demo.
const WINDOW_MS = 10 * 60_000;
const PER_WINDOW = 20;
const seen = new Map<string, number[]>();

function client(request: Request): string {
  // The HTTPS proxy appends the address it saw last, so the last entry is the one nobody can forge. Behind
  // Cloudflare that is a Cloudflare edge shared by many visitors, so the visitor's own address (which
  // Cloudflare sets) is added to it: someone reaching the server directly could forge that header to get
  // more buckets, which the API's own limits (sign-ups per hour, companies in all) still bound.
  const forwarded = request.headers.get("x-forwarded-for")?.split(",").map((s) => s.trim()).filter(Boolean);
  const edge = forwarded?.at(-1) ?? "local";
  const visitor = request.headers.get("cf-connecting-ip")?.trim().slice(0, 64);
  return visitor ? `${edge}/${visitor}` : edge;
}

function allowed(who: string): boolean {
  const now = Date.now();
  if (seen.size > 5_000) seen.clear();
  const recent = (seen.get(who) ?? []).filter((t) => now - t < WINDOW_MS);
  if (recent.length >= PER_WINDOW) return false;
  recent.push(now);
  seen.set(who, recent);
  return true;
}

/** Sign in with a password, or sign up (a new company, or a creator joining one). Same-site JSON only,
 * like the token sign-in; on success the new token goes into the session cookie and never to the page. */
export async function POST(request: Request) {
  if (crossOrigin(request)
    || !(request.headers.get("content-type") ?? "").toLowerCase().startsWith("application/json")) {
    return Response.json({ error: "Sign in from this console." }, { status: 403 });
  }
  if (!API_URL) return Response.json({ error: "No Verytas API is configured here." }, { status: 503 });
  if (!allowed(client(request))) return Response.json({ error: "Too many attempts. Try again in a few minutes." }, { status: 429 });
  const parsed = Input.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    const pw = parsed.error.issues.some((i) => i.path[0] === "password");
    return Response.json({ error: pw ? "Use a password of at least 10 characters." : "Please check the form." }, { status: 400 });
  }
  const { action, ...fields } = parsed.data;
  const path = action === "signin" ? "/accounts/signin" : "/accounts/signup";
  const body = action === "signin" ? fields : { kind: action, ...fields };
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), cache: "no-store", signal: AbortSignal.timeout(15_000) });
  } catch {
    return Response.json({ error: "The Verytas API did not respond." }, { status: 502 });
  }
  const out = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof out?.detail === "string" ? out.detail : null;
    const said = detail ? detail.charAt(0).toUpperCase() + detail.slice(1) + "." : "That didn't work. Please try again.";
    return Response.json({ error: res.status === 404 && action === "signin" ? "Accounts can't be made on this server." : said },
      { status: res.status === 422 ? 400 : res.status });
  }
  (await cookies()).set(SESSION_COOKIE, out.token, cookieOptions());
  return Response.json({ name: out.user?.name, role: out.user?.role, company: out.company, joinCode: out.join_code ?? null });
}

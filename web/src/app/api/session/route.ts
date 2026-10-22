import { cookies } from "next/headers";
import { z } from "zod/v4";
import { SESSION_COOKIE, cookieOptions, signinRequired } from "@/lib/session";

const API_URL = process.env.VERYTAS_API_URL;
const Input = z.object({ token: z.string().trim().min(16).max(512).regex(/^[\w.\-~+/=]+$/) });

/** Whether this console asks people to sign in (the settings menu shows sign-out only then). */
export async function GET() {
  return Response.json({ required: signinRequired });
}

/** Sign in: the token is checked against the API before it is stored. */
export async function POST(request: Request) {
  if (!API_URL) return Response.json({ error: "No Verytas API is configured; this console runs on demo data." }, { status: 503 });
  const parsed = Input.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return Response.json({ error: "That doesn't look like a Verytas token." }, { status: 400 });
  let res: Response;
  try {
    res = await fetch(`${API_URL}/me`, {
      headers: { Authorization: `Bearer ${parsed.data.token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return Response.json({ error: "The Verytas API did not respond." }, { status: 502 });
  }
  if (res.status === 401 || res.status === 403) return Response.json({ error: "That token was not accepted." }, { status: 401 });
  if (!res.ok) return Response.json({ error: "The Verytas API could not check the token." }, { status: 502 });
  (await cookies()).set(SESSION_COOKIE, parsed.data.token, cookieOptions());
  return Response.json(await res.json());
}

export async function DELETE() {
  (await cookies()).delete(SESSION_COOKIE);
  return new Response(null, { status: 204 });
}

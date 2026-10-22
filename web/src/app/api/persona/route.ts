import { cookies } from "next/headers";
import { cookieOptions, currentPersona, PERSONA_COOKIE, personasAvailable } from "@/lib/session";

/** Which side of the console this browser is viewing, and whether it can switch (sign-in off only). */
export async function GET() {
  return Response.json({ available: personasAvailable, persona: await currentPersona() });
}

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== new URL(request.url).host) {
    return Response.json({ error: "cross-site request refused" }, { status: 403 });
  }
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    return Response.json({ error: "send JSON" }, { status: 415 });
  }
  if (!personasAvailable) return Response.json({ error: "Switching views needs sign-in to be off and a creator account." }, { status: 404 });
  const body = await request.json().catch(() => null) as { persona?: unknown } | null;
  if (body?.persona !== "manager" && body?.persona !== "creator") {
    return Response.json({ error: "persona must be manager or creator" }, { status: 400 });
  }
  (await cookies()).set(PERSONA_COOKIE, body.persona, cookieOptions());
  return Response.json({ persona: body.persona });
}

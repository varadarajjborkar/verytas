import { backendConfigured, forward } from "@/lib/backend";
import { sessionToken } from "@/lib/session";

// One server-side door to the Verytas API for the console. Calls go out as the
// signed-in person, and only these get through; the API then checks that
// person's role on each one (library writes are brand-admin only). The audit
// log, account creation and bootstrap stay out of reach of the browser.
// With sign-in off, every visitor acts as the configured service account,
// which is why sign-in must be on before this is reachable by anyone else.
const ALLOWED: [string, RegExp][] = [
  ["POST", /^media$/],
  ["POST", /^contents\/precheck$/],
  ["POST", /^contents$/],
  ["GET", /^reviews\/\d+$/],
  ["GET", /^contents\/\d+$/],
  ["POST", /^contents\/\d+\/resubmit$/],
  ["POST", /^contents\/\d+\/ai-edit$/],
  ["GET", /^contents\/\d+\/disputes$/],
  ["POST", /^findings\/\d+\/disputes$/],
  ["POST", /^findings\/\d+\/decision$/],
  ["GET", /^brand-assets$/],
  ["GET", /^me$/],
  ["GET", /^contents$/],
  ["POST", /^contents\/\d+\/transition$/],
  ["GET", /^chats$/],
  ["POST", /^chats$/],
  ["GET", /^chats\/\d+$/],
  ["PUT", /^chats\/\d+$/],
  ["DELETE", /^chats\/\d+$/],
  // A piece's shared history, comments and the people named in it.
  ["GET", /^contents\/\d+\/timeline$/],
  ["GET", /^contents\/\d+\/comments$/],
  ["POST", /^contents\/\d+\/comments$/],
  ["GET", /^users$/],
  // The brand library. Reads are open to the workspace; the API allows writes to brand admins only.
  ["GET", /^rules$/],
  ["POST", /^rules$/],
  ["PATCH", /^rules\/\d+$/],
  ["POST", /^rules\/extract$/],
  ["GET", /^facts$/],
  ["POST", /^facts$/],
  ["POST", /^facts\/\d+\/retire$/],
  ["GET", /^confidential-terms$/],
  ["POST", /^confidential-terms$/],
  ["PATCH", /^confidential-terms\/\d+$/],
  ["DELETE", /^confidential-terms\/\d+$/],
  ["POST", /^brand-assets$/],
  ["DELETE", /^brand-assets\/\d+$/],
  ["GET", /^brand-assets\/\d+\/image$/],
  // Escalations to a person, brand events and the public-contacts register.
  ["POST", /^findings\/\d+\/escalations$/],
  ["GET", /^escalations$/],
  ["GET", /^escalations\/count$/],
  ["GET", /^escalations\/\d+$/],
  ["POST", /^escalations\/\d+\/(?:resolve|withdraw)$/],
  ["GET", /^events$/],
  ["POST", /^events$/],
  ["PATCH", /^events\/\d+$/],
  ["POST", /^events\/\d+\/cancel$/],
  ["GET", /^events\/\d+\/impacts$/],
  ["GET", /^public-contacts$/],
  ["POST", /^public-contacts$/],
  ["DELETE", /^public-contacts\/\d+$/],
];
// Uploads are forwarded as-is; the API sniffs and limits them again.
const MAX_BODY = 150 * 1024 * 1024;

/**
 * The request body as a stream that stops once it passes `limit` bytes,
 * whatever Content-Length claimed. The API then sees a cut-off body and
 * answers with its own error, so `tripped()` tells the caller to answer 413.
 */
function capped(body: ReadableStream<Uint8Array>, limit: number) {
  let seen = 0;
  let over = false;
  const stream = body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      seen += chunk.byteLength;
      if (seen > limit) {
        over = true;
        controller.error(new Error("request body over the limit"));
      } else {
        controller.enqueue(chunk);
      }
    },
  }));
  return { stream, tripped: () => over };
}

async function handle(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const path = (await ctx.params).path.join("/");
  if (!ALLOWED.some(([m, re]) => m === request.method && re.test(path))) {
    return Response.json({ error: "not available from the browser" }, { status: 404 });
  }
  if (!backendConfigured) {
    return Response.json({ error: "The Verytas API is not configured, so this page runs on demo data.", demo: true },
      { status: 503 });
  }
  // Not behind proxy.ts (see its matcher), so the same-site check lives here too.
  const origin = request.headers.get("origin");
  if (request.method !== "GET" && origin && new URL(origin).host !== new URL(request.url).host) {
    return Response.json({ error: "cross-site request refused" }, { status: 403 });
  }
  const token = await sessionToken();
  if (!token) return Response.json({ error: "Sign in first." }, { status: 401 });
  const tooLarge = Response.json({ error: "That file is over 150 MB." }, { status: 413 });
  // Content-Length is a fast early answer only; the stream cap is what holds.
  if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY) return tooLarge;
  const body = request.method === "GET" || request.method === "DELETE" || !request.body ? undefined : capped(request.body, MAX_BODY);
  const tripped = () => body?.tripped() ?? false;
  const query = new URL(request.url).search;
  try {
    const res = await forward(request.method, `/${path}${query}`, body?.stream, request.headers.get("content-type"), token);
    if (tripped()) return tooLarge;
    if (res.status === 401) {
      return Response.json({ error: "Your session has expired. Sign in again." }, { status: 401 });
    }
    const headers: Record<string, string> = { "content-type": res.headers.get("content-type") ?? "application/json" };
    // Asset thumbnails: cacheable for this person only, and never sniffed into something else.
    const cache = res.headers.get("cache-control");
    if (cache?.startsWith("private")) headers["cache-control"] = cache;
    if (res.headers.get("x-content-type-options")) headers["x-content-type-options"] = "nosniff";
    return new Response(res.status === 204 ? null : res.body, { status: res.status, headers });
  } catch (err) {
    if (tripped()) return tooLarge;
    console.error("[verytas] proxy failed:", (err as Error).message);
    return Response.json({ error: "The review service did not respond. Try again in a moment." }, { status: 502 });
  }
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;

import { backendConfigured, forward } from "@/lib/backend";
import { sessionToken } from "@/lib/session";
import { crossOrigin } from "@/lib/same-origin";
import { isSafeMessage, statusMessage } from "@/lib/errors";

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
  ["GET", /^contents\/\d+\/versions\/\d+\/images\/[A-Za-z0-9_-]{1,40}$/],
  // A document's page pictures and where its findings sit on them (built on request).
  ["GET", /^contents\/\d+\/versions\/\d+\/documents\/[A-Za-z0-9_-]{1,40}\/preview$/],
  ["GET", /^contents\/\d+\/versions\/\d+\/documents\/[A-Za-z0-9_-]{1,40}\/pages\/\d{1,3}$/],
  ["POST", /^contents\/\d+\/resubmit$/],
  ["POST", /^contents\/\d+\/ai-edit$/],
  ["GET", /^contents\/\d+\/disputes$/],
  ["POST", /^findings\/\d+\/disputes$/],
  ["POST", /^findings\/\d+\/decision$/],
  ["GET", /^brand-assets$/],
  ["GET", /^me$/],
  // Personal tokens for the person's own AI client. Managed here with the web session, never over /mcp.
  ["GET", /^me\/tokens$/],
  ["POST", /^me\/tokens$/],
  ["DELETE", /^me\/tokens\/\d+$/],
  // What Inki keeps about the person from Ask Inki; the API scopes it to them.
  // What happened on the pieces this person waits on (the dashboard, the sign-in notice and the nav badge),
  // and marking a piece opened.
  ["GET", /^me\/news$/],
  ["POST", /^contents\/\d+\/seen$/],
  ["GET", /^me\/memories$/],
  ["DELETE", /^me\/memories$/],
  ["DELETE", /^me\/memories\/[0-9a-fA-F-]{32,36}$/],
  // The global search bar; the API scopes every hit to what this person may open.
  ["GET", /^search$/],
  // A self-serve company's join code, for its brand admin (the API refuses everyone else).
  ["GET", /^accounts\/join-code$/],
  ["GET", /^onboarding$/],
  ["POST", /^onboarding\/sample-kit$/],
  ["GET", /^contents$/],
  ["POST", /^contents\/\d+\/transition$/],
  ["GET", /^chats$/],
  ["POST", /^chats$/],
  ["GET", /^chats\/\d+$/],
  ["PUT", /^chats\/\d+$/],
  ["DELETE", /^chats\/\d+$/],
  // Conversations between a creator and the brand team; the API checks each one is the caller's.
  ["GET", /^conversations$/],
  ["POST", /^conversations$/],
  ["GET", /^conversations\/(?:people|unread|stream|inki-consent)$/],
  ["POST", /^conversations\/inki-consent$/],
  ["DELETE", /^conversations\/inki-consent$/],
  ["GET", /^conversations\/\d+\/messages$/],
  ["POST", /^conversations\/\d+\/(?:messages|read)$/],
  ["PATCH", /^conversations\/\d+\/messages\/\d+$/],
  ["DELETE", /^conversations\/\d+\/messages\/\d+$/],
  // Files shared in a conversation, shown in place (ranged, so a video can be sought) and their previews.
  ["GET", /^conversations\/\d+\/files\/[0-9a-f]{32}(?:\/poster)?$/],
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
  ["POST", /^rules\/\d+\/clarify$/],
  // Prism Intake (brand admins; the API checks the role on each call).
  ["POST", /^intake\/files$/],
  ["POST", /^intake$/],
  ["GET", /^intake$/],
  ["GET", /^intake\/\d+$/],
  ["POST", /^intake\/items\/\d+\/(?:answer|refresh)$/],
  ["POST", /^intake\/drafts\/\d+$/],
  ["POST", /^intake\/\d+\/decide$/],
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
  ["GET", /^insights\/creators$/],
  // How pieces did once live (api/results.py).
  ["GET", /^contents\/\d+\/result$/],
  ["PUT", /^contents\/\d+\/result$/],
  ["DELETE", /^contents\/\d+\/result$/],
  ["POST", /^results\/import$/],
  ["GET", /^insights\/performance$/],
  ["GET", /^insights\/creators\/\d+$/],
  ["GET", /^escalations\/count$/],
  ["GET", /^escalations\/\d+$/],
  ["POST", /^escalations\/\d+\/(?:resolve|withdraw)$/],
  ["GET", /^events$/],
  ["POST", /^events$/],
  ["PATCH", /^events\/\d+$/],
  ["POST", /^events\/\d+\/cancel$/],
  ["GET", /^events\/\d+\/impacts$/],
  // Approved people: who may appear in content, their dates and reference photos (writes are brand admin only).
  ["GET", /^people$/],
  ["POST", /^people$/],
  ["PATCH", /^people\/\d+$/],
  ["POST", /^people\/\d+\/references$/],
  ["DELETE", /^people\/\d+\/references\/\d+$/],
  ["GET", /^people\/\d+\/references\/\d+\/image$/],
  // A version's video, streamed in ranges for the review player.
  ["GET", /^contents\/\d+\/versions\/\d+\/videos\/[A-Za-z0-9_-]{1,40}$/],
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
  if (request.method !== "GET" && crossOrigin(request)) {
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
    const res = await forward(request.method, `/${path}${query}`, body?.stream, request.headers.get("content-type"), token,
      request.headers.get("range"));
    if (tripped()) return tooLarge;
    if (res.status === 401) {
      return Response.json({ error: "Your session has expired. Sign in again." }, { status: 401 });
    }
    if (res.status >= 500) return await serverFailure(res, path);
    const headers: Record<string, string> = { "content-type": res.headers.get("content-type") ?? "application/json" };
    // Asset thumbnails: cacheable for this person only, and never sniffed into something else.
    const cache = res.headers.get("cache-control");
    if (cache?.startsWith("private")) headers["cache-control"] = cache;
    if (res.headers.get("x-content-type-options")) headers["x-content-type-options"] = "nosniff";
    // A conversation's files are played and shown in place: ranges pass through, and they stay inline.
    for (const h of ["accept-ranges", "content-range", "content-length", "content-disposition", "content-security-policy"]) {
      const v = res.headers.get(h);
      if (v) headers[h] = v;
    }
    return new Response(res.status === 204 ? null : res.body, { status: res.status, headers });
  } catch (err) {
    if (tripped()) return tooLarge;
    console.error("[verytas] proxy failed:", (err as Error).message);
    return Response.json({ error: "The review service did not respond. Try again in a moment." }, { status: 502 });
  }
}

/** A failure on the API's side. Its own sentence passes through when it was written for people (a
 * worker that is starting, a service that is busy); a traceback, a plain-text 500 or anything else is logged
 * here and replaced, so no internals reach the page. */
async function serverFailure(res: Response, path: string): Promise<Response> {
  const text = await res.text().catch(() => "");
  let said: unknown;
  try {
    const body = JSON.parse(text) as { detail?: unknown; error?: unknown };
    said = typeof body.detail === "string" ? body.detail : (body.detail as { message?: unknown })?.message ?? body.error;
  } catch {
    said = undefined;
  }
  // Only the sentence passes; any other field the failure carried stays on this side.
  if (isSafeMessage(said)) return Response.json({ detail: said }, { status: res.status });
  console.error(`[verytas] API ${res.status} on /${path}:`, text.slice(0, 300));
  return Response.json({ error: statusMessage(res.status) }, { status: res.status });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;

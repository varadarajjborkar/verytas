import { NextResponse, type NextRequest } from "next/server";

// An optimistic gate in front of every page and API route: no session cookie,
// no entry. It only checks that a cookie exists; the API checks the token
// itself on every call, so a forged cookie gets no further than a 401.
const SESSION_COOKIE = "vt_session";
const backendConfigured = Boolean(process.env.VERYTAS_API_URL);
const devAutologin = process.env.NODE_ENV !== "production" && process.env.VERYTAS_DEV_AUTOLOGIN === "1";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const api = pathname.startsWith("/api/");

  // Defence in depth for state-changing calls: they must come from this site.
  if (api && request.method !== "GET" && request.method !== "HEAD") {
    const origin = request.headers.get("origin");
    if (origin && new URL(origin).host !== request.nextUrl.host) {
      return NextResponse.json({ error: "cross-site request refused" }, { status: 403 });
    }
  }
  // Demo mode has no accounts to sign in to; there is nothing behind the gate.
  if (!backendConfigured || devAutologin || request.cookies.get(SESSION_COOKIE)?.value) {
    return NextResponse.next();
  }
  if (api) return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  const signin = new URL("/signin", request.url);
  signin.searchParams.set("next", pathname + request.nextUrl.search);
  return NextResponse.redirect(signin);
}

export const config = {
  // Everything except the sign-in page, its API and static assets, and the
  // upload proxy: Next keeps only the first 10 MB of a body that passes
  // through here, and uploads go to 150 MB. app/api/v checks the session and
  // origin itself and streams the body under its own cap.
  matcher: ["/((?!signin|api/session|api/v/|_next/static|_next/image|favicon.ico).*)"],
};

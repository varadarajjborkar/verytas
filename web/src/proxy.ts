import { NextResponse, type NextRequest } from "next/server";
import { APP, ONLY_FOR, SESSION_COOKIE } from "@/lib/app";
import { crossOrigin } from "@/lib/same-origin";

// An optimistic gate in front of every page and API route: no session cookie,
// no entry. It only checks that a cookie exists; the API checks the token
// itself on every call, so a forged cookie gets no further than a 401.
const backendConfigured = Boolean(process.env.VERYTAS_API_URL);
// Off until VERYTAS_REQUIRE_SIGNIN=1 (see lib/session.ts).
const signinRequired = process.env.VERYTAS_REQUIRE_SIGNIN === "1";
const devAutologin = process.env.NODE_ENV !== "production" && process.env.VERYTAS_DEV_AUTOLOGIN === "1";


export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const api = pathname.startsWith("/api/");

  // Each app serves only its own side's screens.
  const owner = Object.entries(ONLY_FOR).find(([p]) => pathname === p || pathname.startsWith(`${p}/`))?.[1];
  if (APP && owner && owner !== APP) return NextResponse.redirect(new URL("/", request.url));

  // Defence in depth for state-changing calls: they must come from this site.
  if (api && request.method !== "GET" && request.method !== "HEAD") {
    if (crossOrigin(request)) {
      return NextResponse.json({ error: "cross-site request refused" }, { status: 403 });
    }
  }
  // The public pages (public/welcome): privacy and terms for anyone.
  if (pathname === "/privacy" || pathname === "/terms") {
    return NextResponse.rewrite(new URL(`/welcome${pathname}.html`, request.url));
  }
  // Demo mode has no accounts to sign in to; there is nothing behind the gate.
  if (!signinRequired || !backendConfigured || devAutologin || request.cookies.get(SESSION_COOKIE)?.value) {
    return NextResponse.next();
  }
  if (api) return NextResponse.json({ error: "Sign in first." }, { status: 401 });
  // Someone arriving at the front door without a session sees the landing page, which leads to the demo
  // and to sign up; any deeper link still goes to sign in and comes back.
  if (pathname === "/") return NextResponse.rewrite(new URL("/welcome/index.html", request.url));
  const signin = new URL("/signin", request.url);
  signin.searchParams.set("next", pathname + request.nextUrl.search);
  return NextResponse.redirect(signin);
}

export const config = {
  // Everything except the sign-in page, its API and static assets, and the
  // upload proxy: Next keeps only the first 10 MB of a body that passes
  // through here, and uploads go to 150 MB. app/api/v checks the session and
  // origin itself and streams the body under its own cap.
  matcher: ["/((?!signin|api/session|api/v/|_next/static|_next/image|favicon.ico|icon.svg|apple-icon.png|inki.png|inki-wink.png|inki-eye.png|welcome/).*)"],
};

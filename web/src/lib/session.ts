import "server-only";

import { cookies } from "next/headers";

// Each person signs in with their own Verytas API token. It lives in an
// httpOnly cookie, so page scripts can't read it, and every call to the API is
// made as that person: the backend's roles and tiers apply, not a shared
// service account's. SameSite=Strict keeps other sites from riding on it.
export const SESSION_COOKIE = "vt_session";
export const SESSION_MAX_AGE_S = 12 * 60 * 60;

// Sign-in is off until VERYTAS_REQUIRE_SIGNIN=1. While off, every visitor
// acts as the service account (VERYTAS_API_TOKEN): fine on a laptop, not on a
// shared host. While on, the service token is used only with the explicit
// local-development opt-in, never in a production build.
export const signinRequired = process.env.VERYTAS_REQUIRE_SIGNIN === "1";
const DEV_TOKEN = !signinRequired
  ? process.env.VERYTAS_API_TOKEN
  : process.env.NODE_ENV !== "production" && process.env.VERYTAS_DEV_AUTOLOGIN === "1"
    ? process.env.VERYTAS_API_TOKEN
    : undefined;

export async function sessionToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value || DEV_TOKEN || null;
}

export function cookieOptions() {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  };
}

import "server-only";

import { cookies } from "next/headers";

// Each person signs in with their own Verytas API token. It lives in an
// httpOnly cookie, so page scripts can't read it, and every call to the API is
// made as that person: the backend's roles and tiers apply, not a shared
// service account's. SameSite=Strict keeps other sites from riding on it.
export const SESSION_COOKIE = "vt_session";
export const SESSION_MAX_AGE_S = 12 * 60 * 60;

// Local development only: an explicit opt-in that signs every visitor in as
// the service account. Ignored in production builds.
const DEV_TOKEN =
  process.env.NODE_ENV !== "production" && process.env.VERYTAS_DEV_AUTOLOGIN === "1"
    ? process.env.VERYTAS_API_TOKEN
    : undefined;

export const devAutologin = Boolean(DEV_TOKEN);

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

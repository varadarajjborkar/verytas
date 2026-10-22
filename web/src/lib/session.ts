import "server-only";

import { cookies } from "next/headers";
import { APP, SESSION_COOKIE as APP_SESSION_COOKIE } from "./app";

// Each person signs in with their own Verytas API token. It lives in an
// httpOnly cookie, so page scripts can't read it, and every call to the API is
// made as that person: the backend's roles and tiers apply, not a shared
// service account's. SameSite=Strict keeps other sites from riding on it.
export const SESSION_COOKIE = APP_SESSION_COOKIE;
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

// With sign-in off there is no login to tell the two sides apart, so a second
// account (VERYTAS_CREATOR_TOKEN) lets one browser view the console as a creator.
// Both are real accounts: the API still enforces each one's role, so switching
// changes what is allowed, not just what is shown. Never honoured once sign-in is on.
export const PERSONA_COOKIE = "vt_persona";
export type Persona = "manager" | "creator";
const CREATOR_TOKEN = !signinRequired ? process.env.VERYTAS_CREATOR_TOKEN : undefined;
// A server fixed to one side (lib/app.ts) never switches: it is that side's app.
export const personasAvailable = APP === null && Boolean(DEV_TOKEN && CREATOR_TOKEN);

export async function currentPersona(): Promise<Persona> {
  if (APP) return APP;
  return (await cookies()).get(PERSONA_COOKIE)?.value === "creator" ? "creator" : "manager";
}

export async function sessionToken(): Promise<string | null> {
  const jar = await cookies();
  const own = jar.get(SESSION_COOKIE)?.value;
  if (own) return own;
  // With sign-in off, a fixed app uses its side's demo account and nothing else.
  if (APP === "creator") return CREATOR_TOKEN || null;
  if (APP === "manager") return DEV_TOKEN || null;
  if (CREATOR_TOKEN && jar.get(PERSONA_COOKIE)?.value === "creator") return CREATOR_TOKEN;
  return DEV_TOKEN || null;
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

// A random id per browser, so a shared demo person's Ask Inki memory is kept per visitor rather than pooled
// across everyone who picks that person (backend memory/personal.py). It names a browser, not a person, carries
// nothing else, and only rides along to the API on shared sign-ins (lib/backend.ts). Not imported as
// server-only: the proxy issues it.
// __Host- in production, like the session cookie: no other host under a shared parent domain can plant one.
export const DEVICE_COOKIE = process.env.NODE_ENV === "production" ? "__Host-vt_device" : "vt_device";
export const DEVICE_HEADER = "X-Verytas-Device";
const DEVICE = /^[A-Za-z0-9_-]{16,64}$/;

export const validDevice = (v: string | undefined | null): v is string => Boolean(v && DEVICE.test(v));

export function newDeviceId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function deviceCookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 180 * 24 * 60 * 60,
  };
}

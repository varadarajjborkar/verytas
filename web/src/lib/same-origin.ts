// Whether a request was sent from a page on another site. Browsers always set Origin on cross-site
// writes and can't forge it, so it is compared with the Host the browser addressed. Not with
// request.url: behind the HTTPS proxy that carries the app's own bind address (127.0.0.1:3000),
// and every same-site request would look foreign.
export function crossOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("host");
  try {
    return !host || new URL(origin).host !== host;
  } catch {
    return true; // "null" or garbage: not a page on this site
  }
}

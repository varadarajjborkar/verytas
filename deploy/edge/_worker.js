// The demo's public address (verytas.pages.dev) on Cloudflare's free tier. It holds no app code: every
// request is passed to the AWS server as is, so there is one deployment to keep current, not two.
const UPSTREAM = "https://15-252-228-168.sslip.io";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const self = url.origin;
    // The path is set on a copy of UPSTREAM, never resolved against it: resolved, "//elsewhere.example/x"
    // is a scheme-relative reference and would send the visitor's cookies to that host and serve its
    // answer as ours.
    const target = new URL(UPSTREAM);
    target.pathname = url.pathname;
    target.search = url.search;
    if (target.origin !== UPSTREAM) return new Response("Bad request", { status: 400 });

    const headers = new Headers(request.headers);
    // The app accepts a write only when its Origin matches the host the browser addressed. Our own pages
    // are restated as the upstream's; any other origin passes through untouched and is refused there.
    if (headers.get("origin") === self) headers.set("origin", UPSTREAM);
    const referer = headers.get("referer");
    if (referer?.startsWith(self + "/")) headers.set("referer", UPSTREAM + referer.slice(self.length));
    headers.set("x-forwarded-host", url.host);

    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    });
    const response = new Response(upstream.body, upstream);
    const location = response.headers.get("location");
    if (location) {
      const to = new URL(location, UPSTREAM);
      if (to.origin === UPSTREAM) response.headers.set("location", self + to.pathname + to.search + to.hash);
    }
    return response;
  },
};

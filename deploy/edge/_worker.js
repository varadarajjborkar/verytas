// The demo's public address (verytas.pages.dev) on Cloudflare's free tier. It holds no app code: every
// request is passed to the AWS server as is, so there is one deployment to keep current, not two.
const UPSTREAM = "https://15-252-228-168.sslip.io";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const self = url.origin;
    const headers = new Headers(request.headers);
    // The app accepts a write only when its Origin matches the host the browser addressed. Our own pages
    // are restated as the upstream's; any other origin passes through untouched and is refused there.
    if (headers.get("origin") === self) headers.set("origin", UPSTREAM);
    const referer = headers.get("referer");
    if (referer?.startsWith(self + "/")) headers.set("referer", UPSTREAM + referer.slice(self.length));
    headers.set("x-forwarded-host", url.host);

    const upstream = await fetch(new URL(url.pathname + url.search, UPSTREAM), {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      redirect: "manual",
    });
    const response = new Response(upstream.body, upstream);
    const location = response.headers.get("location");
    if (location?.startsWith(UPSTREAM)) response.headers.set("location", self + location.slice(UPSTREAM.length));
    return response;
  },
};

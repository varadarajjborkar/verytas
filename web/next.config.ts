import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  // The brand-team and creator apps run side by side from this folder (package.json dev:*), each with
  // its own build directory so their dev servers don't share a lock.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The dev-mode badge sits on top of Settings in every corner; off in development too.
  devIndicators: false,
  // No "X-Powered-By: Next.js": the framework and its version are no one else's business.
  poweredByHeader: false,
  partialPrefetching: true,
  // Every image the app shows is its own or one the viewer attached (data: and blob: URLs), so img-src
  // stays on this origin: an image link a model or a pasted post slips into Ask Verytas cannot load,
  // which keeps it from beaconing who read it. Scripts are left to Next for now; nonces would cost the
  // static shells cacheComponents gives us.
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "Content-Security-Policy",
          value: "img-src 'self' data: blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'" },
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      ],
    }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;

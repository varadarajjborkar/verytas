import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  // The brand-team and creator apps run side by side from this folder (package.json dev:*), each with
  // its own build directory so their dev servers don't share a lock.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The dev-mode badge sits on top of Settings in every corner; off in development too.
  devIndicators: false,
  partialPrefetching: true,
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

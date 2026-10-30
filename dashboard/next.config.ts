import type { NextConfig } from "next";

// Origin of the Python FastAPI backend, used by the dev API proxy below.
// Read at build time (Next bakes rewrites into the routes manifest), so set it
// when building for an environment that relies on the proxy. In production the
// dashboard typically sits behind a reverse proxy that routes /api/v1 to the
// backend directly, so this is primarily a local-dev convenience.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Lean production image: copies only what's needed to run `node server.js`.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // Same-origin API: the browser calls /api/v1/*, proxied to the backend so
    // there is no CORS. Applied after filesystem routes, so the dashboard's own
    // /api/assistant/* route handler is matched first.
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_ORIGIN}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;

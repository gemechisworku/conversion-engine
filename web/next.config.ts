import type { NextConfig } from "next";

/**
 * Same-origin proxy for the FastAPI orchestration app.
 * The browser calls `/api/orchestration/*` on the Next host (no CORS preflight to 127.0.0.1:8000).
 * Set `ORCHESTRATION_UPSTREAM_URL` in `web/.env.local` if uvicorn is not on 127.0.0.1:8000.
 */
const upstream = (process.env.ORCHESTRATION_UPSTREAM_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/orchestration/:path*",
        destination: `${upstream}/:path*`,
      },
    ];
  },
};

export default nextConfig;

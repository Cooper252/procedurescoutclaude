import type { NextConfig } from "next";

// API_URL points at the ProcedureScout API (e.g. http://localhost:8000).
// Without it the site runs in preview mode on made-up sample data
// (lib/synthetic_demo.ts), clearly labeled on every page.
// A bare "host:port" (how Render passes a private service address) means http://.
const rawApi = process.env.API_URL?.trim().replace(/\/$/, "");
const apiUrl = rawApi && !/^https?:\/\//.test(rawApi) ? `http://${rawApi}` : rawApi;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  env: { NEXT_PUBLIC_DEMO: apiUrl ? "0" : "1" },
  async rewrites() {
    return apiUrl ? [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }] : [];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
        ],
      },
    ];
  },
};

export default nextConfig;

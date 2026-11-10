import type { NextConfig } from "next";

// API_URL points at the ProcedureScout API (e.g. http://localhost:8000).
// Without it the site runs in preview mode on made-up sample data
// (lib/synthetic_demo.ts), clearly labeled on every page.
// A bare "host:port" (how Render passes a private service address) means http://.
const rawApi = process.env.API_URL?.trim().replace(/\/$/, "");
const apiUrl = rawApi && !/^https?:\/\//.test(rawApi) ? `http://${rawApi}` : rawApi;
// The API address is read when the site is BUILT. On the live host (Render sets
// RENDER=true) a missing address would quietly ship the sample-data preview, so
// stop the build instead.
if (!apiUrl && (process.env.RENDER === "true" || process.env.REQUIRE_API_URL === "1")) {
  throw new Error("API_URL is not set; the live site would show sample data. Set it and rebuild.");
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  env: { NEXT_PUBLIC_DEMO: apiUrl ? "0" : "1" },
  async rewrites() {
    return apiUrl
      ? [
          { source: "/api/:path*", destination: `${apiUrl}/:path*` },
          // review pages for staff (signed in with the email link + authenticator)
          { source: "/admin/:path*", destination: `${apiUrl}/admin/:path*` },
        ]
      : [];
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

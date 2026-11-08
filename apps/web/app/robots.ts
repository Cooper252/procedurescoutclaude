import type { MetadataRoute } from "next";
import { PREVIEW, SITE_URL } from "@/lib/server";

export default function robots(): MetadataRoute.Robots {
  if (PREVIEW) return { rules: { userAgent: "*", disallow: "/" } }; // never index sample data
  return { rules: { userAgent: "*", allow: "/", disallow: ["/admin", "/api"] }, sitemap: `${SITE_URL}/sitemap.xml` };
}

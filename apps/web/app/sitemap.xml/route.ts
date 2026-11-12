import * as data from "@/lib/server";
import { sitemapIds } from "@/lib/sitemaps";

// The list of sitemap files (app/sitemaps/sitemap.ts), at the standard address
// for robots.txt and search consoles.
export const revalidate = 86400;

export async function GET() {
  const files = (await sitemapIds())
    .map((id) => `  <sitemap><loc>${data.SITE_URL}/sitemaps/sitemap/${id}.xml</loc></sitemap>`)
    .join("\n");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${files}\n</sitemapindex>\n`;
  return new Response(xml, { headers: { "Content-Type": "application/xml" } });
}

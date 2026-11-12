import type { MetadataRoute } from "next";
import * as data from "@/lib/server";
import { CHUNK, sitemapIds, stateUrls } from "@/lib/sitemaps";

// Service-by-city pages for search engines, one file per part of a state
// (lib/sitemaps.ts), all listed in /sitemap.xml. Empty in preview mode
// so sample data is never offered for indexing.
export const revalidate = 86400;

export async function generateSitemaps() {
  return (await sitemapIds()).map((id) => ({ id }));
}

export default async function sitemap({ id }: { id: string }): Promise<MetadataRoute.Sitemap> {
  const base = data.SITE_URL;
  if (id === "main" || data.PREVIEW) {
    return ["", "/help-paying", "/bill", "/learn", "/how-it-works", "/providers", "/prices"].map((p) => ({ url: `${base}${p}` }));
  }
  const m = /^([a-z]{2})-(\d{1,3})$/.exec(String(id));
  const state = m?.[1];
  if (!m || !state || !data.STATES[state]) return [];
  const part = Number(m[2]);
  return (await stateUrls(state)).slice(part * CHUNK, (part + 1) * CHUNK).map((url) => ({ url }));
}

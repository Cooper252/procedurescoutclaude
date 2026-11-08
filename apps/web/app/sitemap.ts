import type { MetadataRoute } from "next";
import * as data from "@/lib/server";

// Service-by-city pages for search engines. Empty in preview mode so sample
// data is never offered for indexing.
export const revalidate = 86400;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = data.SITE_URL;
  const fixed = ["", "/help-paying", "/bill", "/learn", "/how-it-works", "/providers", "/prices"].map((p) => ({ url: `${base}${p}` }));
  if (data.PREVIEW) return fixed;
  const services = await data.services();
  const out: MetadataRoute.Sitemap = [...fixed];
  for (const state of Object.keys(data.STATES)) {
    for (const c of await data.cities(state)) {
      out.push({ url: `${base}/prices/${state}/${c.slug}` });
      for (const s of services) out.push({ url: `${base}/prices/${state}/${c.slug}/${s.slug}` });
    }
  }
  return out;
}

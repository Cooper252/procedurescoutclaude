import * as data from "@/lib/server";

// Sitemap files of at most 40,000 addresses (search engines take 50,000 per
// file; one state alone can pass that). 2026-11-12: one file already held
// 31,831 addresses with two states loaded.
export const CHUNK = 40000;

export async function stateUrls(state: string): Promise<string[]> {
  const base = data.SITE_URL;
  const services = await data.services();
  const out: string[] = [];
  for (const c of await data.cities(state)) {
    out.push(`${base}/prices/${state}/${c.slug}`);
    for (const s of services) out.push(`${base}/prices/${state}/${c.slug}/${s.slug}`);
  }
  return out;
}

export async function sitemapIds(): Promise<string[]> {
  const ids = ["main"];
  if (data.PREVIEW) return ids;
  const services = await data.services();
  for (const state of Object.keys(data.STATES)) {
    const n = (await data.cities(state)).length * (services.length + 1);
    for (let i = 0; i * CHUNK < n; i++) ids.push(`${state}-${i}`);
  }
  return ids;
}

// Data for pages rendered on the server (service-by-city and ZIP pages, the
// sitemap). Calls the API directly at API_URL; without it, uses the preview
// data in lib/synthetic_demo.ts. Never imported by client components.

import "server-only";
import * as demo from "./synthetic_demo";
import type { Place, SearchResult, Service } from "./types";

// A bare "host:port" (how Render passes a private service address) means http://.
const RAW_API = process.env.API_URL?.trim().replace(/\/$/, "");
const API = RAW_API && !/^https?:\/\//.test(RAW_API) ? `http://${RAW_API}` : RAW_API;
export const PREVIEW = !API;
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000").replace(/\/$/, "");

export interface CityInfo {
  state: string;
  city: string;
  slug: string;
  lat: string;
  lng: string;
  facilities: number;
}

// Every state and DC (D-048). A state page lists the cities we have data for;
// until a state is loaded its page simply has no cities yet.
export const STATES: Record<string, string> = {
  al: "Alabama", ak: "Alaska", az: "Arizona", ar: "Arkansas", ca: "California", co: "Colorado",
  ct: "Connecticut", de: "Delaware", dc: "District of Columbia", fl: "Florida", ga: "Georgia",
  hi: "Hawaii", id: "Idaho", il: "Illinois", in: "Indiana", ia: "Iowa", ks: "Kansas",
  ky: "Kentucky", la: "Louisiana", me: "Maine", md: "Maryland", ma: "Massachusetts",
  mi: "Michigan", mn: "Minnesota", ms: "Mississippi", mo: "Missouri", mt: "Montana",
  ne: "Nebraska", nv: "Nevada", nh: "New Hampshire", nj: "New Jersey", nm: "New Mexico",
  ny: "New York", nc: "North Carolina", nd: "North Dakota", oh: "Ohio", ok: "Oklahoma",
  or: "Oregon", pa: "Pennsylvania", ri: "Rhode Island", sc: "South Carolina", sd: "South Dakota",
  tn: "Tennessee", tx: "Texas", ut: "Utah", vt: "Vermont", va: "Virginia", wa: "Washington",
  wv: "West Virginia", wi: "Wisconsin", wy: "Wyoming",
};

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: 3600 }, headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function services(): Promise<Service[]> {
  if (PREVIEW) return demo.DEMO_SERVICES;
  return (await get<Service[]>("/v1/services")) ?? [];
}

export async function cities(state: string): Promise<CityInfo[]> {
  if (!STATES[state]) return [];
  if (PREVIEW) return state === "nv" ? demo.DEMO_CITIES : [];
  return (await get<CityInfo[]>(`/v1/places/cities?state=${state.toUpperCase()}`)) ?? [];
}

export async function city(state: string, slug: string): Promise<CityInfo | null> {
  if (!STATES[state] || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) return null;
  if (PREVIEW) return state === "nv" ? demo.DEMO_CITIES.find((c) => c.slug === slug) ?? null : null;
  return get<CityInfo>(`/v1/places/city/${state}/${slug}`);
}

export async function zip(z: string): Promise<Place | null> {
  if (!/^\d{5}$/.test(z)) return null;
  if (PREVIEW) return demo.demoPlace(z);
  return get<Place>(`/v1/places/zip/${z}`);
}

export async function search(lat: string, lng: string, service: string, radius = "25"): Promise<SearchResult | null> {
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(service)) return null;
  if (PREVIEW) return demo.demoSearch(service, "cash", null, null, radius);
  const qs = new URLSearchParams({ lat, lng, service, radius_miles: radius, mode: "cash" });
  return get<SearchResult>(`/v1/search?${qs.toString()}`);
}

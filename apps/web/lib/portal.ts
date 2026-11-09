// Provider homepages, reviews, counts and the provider portal (D-050).
// The only client for /api/v1/portal, /reviews, /events and /facilities/{id}/page.
// In preview mode (no API) everything answers from lib/synthetic_portal_demo.ts
// and nothing is saved.

import { DEMO, ApiError } from "./api";
import * as demo from "./synthetic_portal_demo";

export type Profile = {
  about: string | null;
  website_url: string | null;
  booking_url: string | null;
  phone: string | null;
  hours: Record<string, string>;
  languages: string[];
  accessibility: string[];
  insurance_note: string | null;
  social_urls: string[];
};

export type Review = {
  id: string;
  rating: number;
  title: string | null;
  body: string;
  price_matched: boolean | null;
  display_name: string;
  verification: "email" | "provider_invite";
  published_at: string;
  reply_body: string | null;
  reply_at: string | null;
};

export type ReviewSummary = {
  average: string | null;
  count: number;
  removed: number;
  price_matched_yes: number;
  price_matched_answered: number;
  stars: number[];
};

export type ProviderPage = {
  facility_id: string;
  claimed: boolean;
  profile: (Profile & { updated_at: string | null }) | null;
  logo_url: string | null;
  photos: { url: string; alt: string | null }[];
  reviews: ReviewSummary;
  latest_reviews: Review[];
  reviews_enabled: boolean;
};

export type Membership = { facility_id: string; facility_name: string; role: string; status: string };
export type Me = {
  email: string;
  display_name: string | null;
  mfa_enabled: boolean;
  mfa_passed: boolean;
  memberships: Membership[];
};
export type MediaItem = { id: string; kind: "logo" | "photo"; status: string; alt_text: string | null; url: string };
export type ProfileEdit = {
  status: "new" | "draft" | "pending_review" | "published";
  profile: Profile;
  rejected_note: string | null;
  media: MediaItem[];
  languages: string[];
  accessibility: string[];
};
export type Num = { value: number | null; previous: number | null };
export type ServiceDemand = {
  service_key: string;
  name: string;
  searches_10: number | null;
  searches_25: number | null;
  searches_50: number | null;
  shown: number | null;
  offered: boolean;
};
export type Boost = {
  service_key: string;
  name: string;
  ring_miles: number;
  searches: number | null;
  estimated_views: number | null;
  current_views: number | null;
};
export type Dashboard = {
  days: number;
  has_location: boolean;
  small_number: number;
  counts: Record<string, Num>;
  average_position: string | null;
  services: ServiceDemand[];
  missed: ServiceDemand[];
  boosts: Boost[];
  sponsors_per_page: number;
};
export type ProviderReview = {
  id: string;
  rating: number;
  title: string | null;
  body: string;
  display_name: string;
  verification: string;
  published_at: string;
  reply_body: string | null;
  reply_status: string | null;
};
export type PublicSpecial = { price: string; who: string; percent_off: string | null; ends_on: string | null; terms: string | null };
export type PublicListing = {
  service_slug: string | null;
  service_name: string | null;
  unit: string | null;
  code: string | null;
  quantity: number;
  regular_price: string;
  updated_at: string | null;
  special: PublicSpecial | null;
};
export type PackageItem = { service_name: string | null; code: string | null; quantity: number };
export type PublicPackage = { name: string; description: string | null; price: string; items: PackageItem[] };
export type ProviderPrices = { listings: PublicListing[]; packages: PublicPackage[] };
export type MyOffer = {
  id: string;
  kind: "special_price" | "percent_off" | "amount_off";
  who: "new_patients" | "everyone";
  offer_price: string | null;
  percent_off: string | null;
  amount_off: string | null;
  starts_on: string;
  ends_on: string | null;
  terms: string | null;
  status: string;
  review_note: string | null;
};
export type MyListing = {
  id: string;
  service_slug: string | null;
  service_name: string | null;
  unit: string | null;
  code_system: string | null;
  code: string | null;
  quantity: number;
  regular_price: string;
  proposed_price: string | null;
  status: string;
  review_note: string | null;
  offers: MyOffer[];
};
export type MyPackage = { id: string; name: string; description: string | null; price: string; status: string; review_note: string | null; items: PackageItem[] };
export type MyPrices = { listings: MyListing[]; packages: MyPackage[] };
export type ListingIn = { service_slug?: string | null; code_system?: string | null; code?: string | null; quantity: number; regular_price: string };
export type OfferIn = { kind: string; who: string; value: string; starts_on: string; ends_on: string | null; terms: string | null };
export type PackageIn = {
  name: string;
  description: string | null;
  price: string;
  items: { service_slug?: string | null; code_system?: string | null; code?: string | null; quantity: number }[];
};
export type Billing = {
  payments_on: boolean;
  fee_starts_on: string | null;
  fee_in_force: boolean;
  content_shown: boolean;
  listing_status: string | null;
  sponsored_status: string | null;
  plans: { code: string; name: string; kind: "listing" | "sponsored"; amount: string; interval: string; can_buy: boolean }[];
  slots: { service_key: string; ring_miles: number }[];
};
export type FacilityHit = { facility_id: string; name: string; city: string | null; state: string; claimed: boolean };

const H = { "Content-Type": "application/json", Accept: "application/json", "X-ProcedureScout": "1" };

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method,
    headers: H,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") msg = j.detail;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(msg, res.status);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const later = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 120));

/** Count a page view or click. Never blocks the page and never fails loudly. */
export function track(facilityId: string, kind: "page_view" | "website_click" | "phone_click" | "directions_click" | "booking_click") {
  if (DEMO || typeof navigator === "undefined") return;
  const body = JSON.stringify({ facility_id: facilityId, kind });
  try {
    if (navigator.sendBeacon) navigator.sendBeacon("/api/v1/events", new Blob([body], { type: "application/json" }));
    else void fetch("/api/v1/events", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true });
  } catch {
    /* counting is best-effort */
  }
}

export const portal = {
  // ---------------------------------------------------------------- public
  page: (id: string): Promise<ProviderPage> => (DEMO ? later(demo.demoPage(id)) : call("GET", `/v1/facilities/${id}/page`)),
  moreReviews: (id: string, offset: number): Promise<Review[]> =>
    DEMO ? later([]) : call("GET", `/v1/facilities/${id}/reviews?offset=${offset}`),
  requestReview: (facilityId: string, email: string): Promise<{ ok: boolean; dev_link: string | null }> =>
    DEMO ? later({ ok: true, dev_link: null }) : call("POST", "/v1/reviews/request", { facility_id: facilityId, email }),
  checkReviewLink: (token: string): Promise<{ facility_id: string; facility_name: string; kind: string }> =>
    DEMO ? later(demo.demoReviewLink()) : call("POST", "/v1/reviews/check", { token }),
  submitReview: (r: {
    token: string;
    rating: number;
    title: string | null;
    body: string;
    price_matched: boolean | null;
    display_name: string;
    visited: boolean;
    independent: boolean;
  }): Promise<{ id: string }> => (DEMO ? later({ id: "preview" }) : call("POST", "/v1/reviews", r)),

  reportPrice: (r: { facility_id: string; problem: string; service_key: string | null; price_shown: string | null; details: string | null }): Promise<{ status: string }> =>
    DEMO ? later({ status: "received" }) : call("POST", "/v1/price-reports", r),
  providerTypesAll: (): Promise<{ code: string; name: string }[]> =>
    DEMO ? later([{ code: "medical_spa", name: "Medical spa" }, { code: "dental_office", name: "Dental office" }]) : call("GET", "/v1/provider-types/all"),
  requestListing: (f: Record<string, string | null>): Promise<{ id: string }> =>
    DEMO ? later({ id: "preview" }) : call("POST", "/v1/portal/listing-requests", f),
  myListingRequests: (): Promise<{ id: string; name: string; status: string; review_note: string | null }[]> =>
    DEMO ? later([]) : call("GET", "/v1/portal/listing-requests"),
  billing: (id: string): Promise<Billing> => (DEMO ? later(demo.demoBilling()) : call("GET", `/v1/portal/facilities/${id}/billing`)),
  checkout: (id: string, plan: string): Promise<{ url: string }> =>
    call("POST", `/v1/portal/facilities/${id}/billing/checkout`, { plan_code: plan }),
  billingPortal: (id: string): Promise<{ url: string }> => call("POST", `/v1/portal/facilities/${id}/billing/portal`),
  providerPrices: (id: string): Promise<ProviderPrices> =>
    DEMO ? later(demo.demoProviderPrices(id)) : call("GET", `/v1/facilities/${id}/provider-prices`),

  // ---------------------------------------------------------------- portal
  myPrices: (id: string): Promise<MyPrices> => (DEMO ? later(demo.demoMyPrices()) : call("GET", `/v1/portal/facilities/${id}/prices`)),
  savePrice: (id: string, body: ListingIn): Promise<{ id: string }> =>
    DEMO ? later({ id: "preview" }) : call("POST", `/v1/portal/facilities/${id}/prices`, body),
  withdrawPrice: (id: string, listingId: string): Promise<void> =>
    DEMO ? later(undefined) : call("DELETE", `/v1/portal/facilities/${id}/prices/${listingId}`),
  addSpecial: (id: string, listingId: string, body: OfferIn): Promise<{ id: string }> =>
    DEMO ? later({ id: "preview" }) : call("POST", `/v1/portal/facilities/${id}/prices/${listingId}/specials`, body),
  withdrawSpecial: (id: string, offerId: string): Promise<void> =>
    DEMO ? later(undefined) : call("DELETE", `/v1/portal/facilities/${id}/specials/${offerId}`),
  addPackage: (id: string, body: PackageIn): Promise<{ id: string }> =>
    DEMO ? later({ id: "preview" }) : call("POST", `/v1/portal/facilities/${id}/packages`, body),
  withdrawPackage: (id: string, packageId: string): Promise<void> =>
    DEMO ? later(undefined) : call("DELETE", `/v1/portal/facilities/${id}/packages/${packageId}`),
  signIn: (email: string): Promise<{ ok: boolean; dev_link: string | null }> =>
    DEMO ? later({ ok: true, dev_link: "/providers/sign-in/verify#preview" }) : call("POST", "/v1/portal/sign-in", { email }),
  verify: (token: string): Promise<Me> => (DEMO ? later(demo.demoMe(false)) : call("POST", "/v1/portal/sign-in/verify", { token })),
  signOut: (): Promise<void> => (DEMO ? later(undefined) : call("POST", "/v1/portal/sign-out")),
  me: (): Promise<Me> => (DEMO ? later(demo.demoMe(true)) : call("GET", "/v1/portal/me")),
  mfaSetup: (): Promise<{ secret: string; otpauth_uri: string }> =>
    DEMO ? later({ secret: "PREVIEWONLYNOTAREALKEY", otpauth_uri: "otpauth://totp/preview" }) : call("POST", "/v1/portal/mfa/setup"),
  mfaVerify: (code: string): Promise<Me> => (DEMO ? later(demo.demoMe(true)) : call("POST", "/v1/portal/mfa/verify", { code })),
  findFacility: (q: string): Promise<FacilityHit[]> =>
    DEMO ? later(demo.demoFind(q)) : call("GET", `/v1/portal/facilities/search?q=${encodeURIComponent(q)}`),
  claim: (facilityId: string, note: string | null): Promise<Membership> =>
    DEMO ? later(demo.demoClaim(facilityId)) : call("POST", "/v1/portal/claims", { facility_id: facilityId, note }),
  profile: (id: string): Promise<ProfileEdit> => (DEMO ? later(demo.demoProfileEdit()) : call("GET", `/v1/portal/facilities/${id}/profile`)),
  saveProfile: (id: string, profile: Profile, submit: boolean): Promise<ProfileEdit> =>
    DEMO
      ? later({ ...demo.demoProfileEdit(), profile, status: submit ? "pending_review" : "draft" })
      : call("PUT", `/v1/portal/facilities/${id}/profile`, { profile, submit }),
  upload: async (id: string, kind: "logo" | "photo", file: File, alt: string): Promise<{ id: string }> => {
    if (DEMO) return later({ id: "preview" });
    const qs = new URLSearchParams({ kind });
    if (alt) qs.set("alt", alt);
    const res = await fetch(`/api/v1/portal/facilities/${id}/media?${qs}`, {
      method: "POST",
      headers: { "X-ProcedureScout": "1", "Content-Type": file.type || "application/octet-stream" },
      credentials: "same-origin",
      body: file,
    });
    if (!res.ok) {
      const j = (await res.json().catch(() => ({}))) as { detail?: string };
      throw new ApiError(j.detail ?? `Upload failed (${res.status})`, res.status);
    }
    return (await res.json()) as { id: string };
  },
  removeMedia: (id: string, mediaId: string): Promise<void> =>
    DEMO ? later(undefined) : call("DELETE", `/v1/portal/facilities/${id}/media/${mediaId}`),
  stats: (id: string, days: number): Promise<Dashboard> =>
    DEMO ? later(demo.demoDashboard(days)) : call("GET", `/v1/portal/facilities/${id}/stats?days=${days}`),
  reviews: (id: string): Promise<{ summary: { average: string | null; count: number; removed: number }; reviews: ProviderReview[] }> =>
    DEMO ? later(demo.demoProviderReviews()) : call("GET", `/v1/portal/facilities/${id}/reviews`),
  invite: (id: string): Promise<{ link: string; expires_in_days: number }> =>
    DEMO ? later({ link: "https://example.com/review#preview-only", expires_in_days: 60 }) : call("POST", `/v1/portal/facilities/${id}/invites`),
  reply: (id: string, reviewId: string, body: string): Promise<{ status: string; privacy_warning: boolean }> =>
    DEMO
      ? later({ status: "pending_review", privacy_warning: /your (visit|procedure)/i.test(body) })
      : call("POST", `/v1/portal/facilities/${id}/reviews/${reviewId}/reply`, { body }),
  report: (id: string, reviewId: string, reason: string): Promise<{ status: string }> =>
    DEMO ? later({ status: "received" }) : call("POST", `/v1/portal/facilities/${id}/reviews/${reviewId}/report`, { reason }),
};

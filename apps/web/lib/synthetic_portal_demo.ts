// SYNTHETIC PREVIEW DATA — made up (CLAUDE.md rule 6).
//
// Shown only in preview mode (no API), so the provider pages and dashboard can
// be seen before hosting. Every name is "Sample …", every review is labeled a
// sample on screen, and every page shows the "Preview: sample data" banner.
// Nothing here is saved or sent anywhere.

import type { Billing, Dashboard, FacilityHit, Me, Membership, MyPrices, ProfileEdit, ProviderPage, ProviderPrices, ProviderReview } from "./portal";

const IMAGING = "d0000000-0000-4000-8000-000000000003";

// A tiny made-up logo (a teal square with a white cross), drawn as SVG.
const LOGO =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='14' fill='#0b6e75'/><path d='M27 14h10v13h13v10H37v13H27V37H14V27h13z' fill='#fff'/></svg>",
  );

const photo = (hue: number, label: string) =>
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 260'><rect width='400' height='260' fill='hsl(${hue},35%,88%)'/><rect x='40' y='60' width='320' height='150' rx='12' fill='hsl(${hue},30%,78%)'/><text x='200' y='145' font-family='system-ui' font-size='20' text-anchor='middle' fill='hsl(${hue},30%,30%)'>${label}</text></svg>`,
  );

export function demoPage(id: string): ProviderPage {
  const empty = { average: null, count: 0, removed: 0, price_matched_yes: 0, price_matched_answered: 0, stars: [0, 0, 0, 0, 0] };
  if (id !== IMAGING) {
    return { facility_id: id, claimed: false, profile: null, logo_url: null, photos: [], reviews: empty, latest_reviews: [], reviews_enabled: true };
  }
  return {
    facility_id: id,
    claimed: true,
    profile: {
      about:
        "Sample Imaging Clinic is a made-up clinic used to preview provider pages. Real providers write a short description here: what they do, who they serve and what makes visiting easy.",
      website_url: "https://example.com",
      booking_url: "https://example.com/book",
      phone: "(000) 555-0130",
      hours: { mon: "07:00-19:00", tue: "07:00-19:00", wed: "07:00-19:00", thu: "07:00-19:00", fri: "07:00-17:00", sat: "08:00-12:00", sun: "closed" },
      languages: ["English", "Spanish", "Tagalog"],
      accessibility: ["wheelchair_access", "accessible_parking", "free_parking", "evening_hours"],
      insurance_note: "Sample note: in network with most major plans. Call to confirm yours.",
      social_urls: [],
      updated_at: "2026-11-01",
    },
    logo_url: LOGO,
    photos: [
      { url: photo(185, "Sample waiting room"), alt: "Sample waiting room" },
      { url: photo(150, "Sample MRI room"), alt: "Sample MRI room" },
      { url: photo(210, "Sample front desk"), alt: "Sample front desk" },
    ],
    reviews: { average: "4.3", count: 3, removed: 1, price_matched_yes: 2, price_matched_answered: 3, stars: [0, 0, 1, 0, 2] },
    latest_reviews: [
      {
        id: "r1",
        rating: 5,
        title: "Sample review: price matched",
        body: "This is a made-up sample review. The price I paid matched the price listed here, and the staff explained everything.",
        price_matched: true,
        display_name: "Sample A.",
        verification: "provider_invite",
        published_at: "2026-10-28",
        reply_body: "Sample reply: thank you for the kind words.",
        reply_at: "2026-10-29",
      },
      {
        id: "r2",
        rating: 5,
        title: null,
        body: "Another made-up sample review. Easy parking and I was in and out in under an hour.",
        price_matched: true,
        display_name: "Sample B.",
        verification: "email",
        published_at: "2026-10-12",
        reply_body: null,
        reply_at: null,
      },
      {
        id: "r3",
        rating: 3,
        title: "Sample review: long wait",
        body: "A made-up mixed sample review. The scan was fine but I waited 40 minutes past my time, and the reading fee was billed separately.",
        price_matched: false,
        display_name: "Sample C.",
        verification: "email",
        published_at: "2026-09-30",
        reply_body: null,
        reply_at: null,
      },
    ],
    reviews_enabled: true,
  };
}

export function demoReviewLink() {
  return { facility_id: IMAGING, facility_name: "Sample Imaging Clinic", kind: "email" };
}

export function demoMe(mfa: boolean): Me {
  return {
    email: "you@example.com",
    display_name: null,
    mfa_enabled: mfa,
    mfa_passed: mfa,
    memberships: [{ facility_id: IMAGING, facility_name: "Sample Imaging Clinic", role: "owner", status: "active" }],
  };
}

export function demoFind(q: string): FacilityHit[] {
  const all: FacilityHit[] = [
    { facility_id: IMAGING, name: "Sample Imaging Clinic", city: "Las Vegas", state: "NV", claimed: true },
    { facility_id: "d0000000-0000-4000-8000-000000000002", name: "Sample Surgery Center", city: "Henderson", state: "NV", claimed: false },
  ];
  return all.filter((f) => f.name.toLowerCase().includes(q.toLowerCase()));
}

export function demoClaim(id: string): Membership {
  return { facility_id: id, facility_name: "Sample Surgery Center", role: "owner", status: "pending" };
}

export function demoProfileEdit(): ProfileEdit {
  const p = demoPage(IMAGING).profile!;
  return {
    status: "published",
    profile: { ...p },
    rejected_note: null,
    media: [
      { id: "m1", kind: "logo", status: "published", alt_text: "Sample logo", url: LOGO },
      { id: "m2", kind: "photo", status: "published", alt_text: "Sample waiting room", url: photo(185, "Sample waiting room") },
      { id: "m3", kind: "photo", status: "pending_review", alt_text: "Sample MRI room", url: photo(150, "Sample MRI room") },
    ],
    languages: ["English", "Spanish", "Tagalog", "Chinese", "Vietnamese", "Korean", "Arabic", "French", "Russian", "Portuguese", "Hindi", "Japanese", "German", "ASL"],
    accessibility: [
      "wheelchair_access",
      "accessible_parking",
      "accessible_restroom",
      "elevator",
      "interpreter_available",
      "free_parking",
      "public_transit_nearby",
      "evening_hours",
      "weekend_hours",
      "telehealth",
    ],
  };
}

export function demoDashboard(days: number): Dashboard {
  const k = days === 7 ? 1 : days === 30 ? 4 : 12;
  const n = (v: number) => (v * k < 10 ? null : v * k);
  return {
    days,
    has_location: true,
    small_number: 10,
    counts: {
      page_view: { value: n(78), previous: n(61) },
      search_impression: { value: n(410), previous: n(372) },
      website_click: { value: n(19), previous: n(14) },
      phone_click: { value: n(11), previous: n(12) },
      directions_click: { value: n(8), previous: n(5) },
      booking_click: { value: n(2), previous: null },
    },
    average_position: "2.4",
    services: [
      { service_key: "svc:mri-brain", name: "MRI of the brain", searches_10: n(55), searches_25: n(88), searches_50: n(97), shown: n(51), offered: true },
      { service_key: "svc:ct-head", name: "CT scan of the head", searches_10: n(40), searches_25: n(66), searches_50: n(70), shown: n(38), offered: true },
      { service_key: "svc:x-ray-chest", name: "Chest X-ray", searches_10: n(31), searches_25: n(47), searches_50: n(52), shown: n(29), offered: true },
    ],
    missed: [
      { service_key: "svc:ultrasound-abdomen", name: "Ultrasound of the belly", searches_10: n(22), searches_25: n(35), searches_50: n(39), shown: null, offered: false },
      { service_key: "svc:mammogram", name: "Screening mammogram", searches_10: n(18), searches_25: n(29), searches_50: n(33), shown: null, offered: false },
    ],
    boosts:
      days === 30
        ? [
            { service_key: "svc:mri-brain", name: "MRI of the brain", ring_miles: 10, searches: 220, estimated_views: 110, current_views: 204 },
            { service_key: "svc:mri-brain", name: "MRI of the brain", ring_miles: 25, searches: 352, estimated_views: 176, current_views: 204 },
            { service_key: "svc:mri-brain", name: "MRI of the brain", ring_miles: 50, searches: 388, estimated_views: 194, current_views: 204 },
            { service_key: "svc:ct-head", name: "CT scan of the head", ring_miles: 10, searches: 160, estimated_views: 80, current_views: 152 },
            { service_key: "svc:ct-head", name: "CT scan of the head", ring_miles: 25, searches: 264, estimated_views: 132, current_views: 152 },
            { service_key: "svc:ct-head", name: "CT scan of the head", ring_miles: 50, searches: 280, estimated_views: 140, current_views: 152 },
          ]
        : [],
    sponsors_per_page: 2,
  };
}

export function demoProviderReviews(): { summary: { average: string | null; count: number; removed: number }; reviews: ProviderReview[] } {
  const p = demoPage(IMAGING);
  return {
    summary: { average: p.reviews.average, count: p.reviews.count, removed: p.reviews.removed },
    reviews: p.latest_reviews.map((r) => ({
      id: r.id,
      rating: r.rating,
      title: r.title,
      body: r.body,
      display_name: r.display_name,
      verification: r.verification,
      published_at: r.published_at,
      reply_body: r.reply_body,
      reply_status: r.reply_body ? "published" : null,
    })),
  };
}

export function demoProviderPrices(id: string): ProviderPrices {
  if (id !== IMAGING) return { listings: [], packages: [] };
  return {
    listings: [
      { service_slug: "mri-brain", service_name: "MRI of the brain", unit: "per_service", code: null, quantity: 1, regular_price: "425", updated_at: "2026-11-01", special: { price: "375", who: "new_patients", percent_off: null, ends_on: "2026-12-31", terms: "Sample special" } },
      { service_slug: "x-ray-chest", service_name: "Chest X-ray", unit: "per_service", code: null, quantity: 1, regular_price: "65", updated_at: "2026-11-01", special: null },
      { service_slug: null, service_name: null, unit: null, code: "CPT 76700", quantity: 1, regular_price: "180", updated_at: "2026-10-20", special: null },
    ],
    packages: [
      { name: "Sample screening pair", description: "A made-up package used only in preview.", price: "220", items: [{ service_name: "Chest X-ray", code: null, quantity: 1 }, { service_name: null, code: "CPT 76700", quantity: 1 }] },
    ],
  };
}

export function demoMyPrices(): MyPrices {
  return {
    listings: [
      { id: "l1", delivery: "in_person", copay_kind: "standard", copay_amount: null, service_slug: "mri-brain", service_name: "MRI of the brain", unit: "per_service", code_system: null, code: null, quantity: 1, regular_price: "425", proposed_price: null, status: "published", review_note: null, offers: [{ id: "o1", kind: "amount_off", who: "new_patients", offer_price: null, percent_off: null, amount_off: "50", starts_on: "2026-11-01", ends_on: "2026-12-31", terms: "Sample special", status: "published", review_note: null }] },
      { id: "l2", delivery: "in_person", copay_kind: null, copay_amount: null, service_slug: "x-ray-chest", service_name: "Chest X-ray", unit: "per_service", code_system: null, code: null, quantity: 1, regular_price: "65", proposed_price: "59", status: "published", review_note: null, offers: [] },
      { id: "l3", delivery: "in_person", copay_kind: null, copay_amount: null, service_slug: null, service_name: null, unit: null, code_system: "CPT", code: "76700", quantity: 1, regular_price: "180", proposed_price: null, status: "pending_review", review_note: null, offers: [] },
    ],
    packages: [{ id: "k1", name: "Sample screening pair", description: "Made up for preview.", price: "220", status: "published", review_note: null, items: [{ service_name: "Chest X-ray", code: null, quantity: 1 }, { service_name: null, code: "CPT 76700", quantity: 1 }] }],
  };
}

export function demoBilling(): Billing {
  return { payments_on: false, fee_starts_on: null, fee_in_force: false, content_shown: true, listing_status: null, sponsored_status: null, plans: [], slots: [] };
}

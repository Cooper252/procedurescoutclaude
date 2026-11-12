// SYNTHETIC PREVIEW DATA — made up, not real prices (CLAUDE.md rule 6).
//
// Used only when the site runs without an API (preview mode), so the design
// can be seen before hosting. Every facility is named "Sample …" and every
// page shows a "Preview: sample data" banner. Nothing here reaches the API,
// the database or a real search.

import type {
  Bundle,
  Estimate,
  FacilityDetail,
  FacilityPrices,
  AssistanceCheck,
  AssistanceMessage,
  Facility,
  Mode,
  NearbyFacility,
  Place,
  Plan,
  Price,
  ProviderType,
  SearchResult,
  Service,
  Suggestion,
} from "./types";

export const DEMO_SERVICES: Service[] = [
  { slug: "mri-brain-without-contrast", name: "MRI of the brain (no contrast)", category: "Imaging", unit: "per_service" },
  { slug: "mri-lower-back-without-contrast", name: "MRI of the lower back (no contrast)", category: "Imaging", unit: "per_service" },
  { slug: "mri-knee-without-contrast", name: "MRI of the knee (no contrast)", category: "Imaging", unit: "per_service" },
  { slug: "ct-head-without-contrast", name: "CT scan of the head (no contrast)", category: "Imaging", unit: "per_service" },
  { slug: "chest-x-ray-two-views", name: "Chest X-ray (2 views)", category: "Imaging", unit: "per_service" },
  { slug: "colonoscopy-diagnostic", name: "Colonoscopy", category: "Procedures", unit: "per_service" },
  { slug: "cataract-surgery", name: "Cataract surgery", category: "Surgery", unit: "per_service" },
  { slug: "knee-arthroscopy-meniscus", name: "Knee arthroscopy (meniscus repair or trim)", category: "Surgery", unit: "per_service" },
  { slug: "blood-panel-comprehensive", name: "Comprehensive metabolic blood panel", category: "Lab tests", unit: "per_service" },
  { slug: "complete-blood-count", name: "Complete blood count (CBC)", category: "Lab tests", unit: "per_service" },
  { slug: "cholesterol-panel", name: "Cholesterol (lipid) panel", category: "Lab tests", unit: "per_service" },
  { slug: "ekg", name: "EKG (heart rhythm test)", category: "Tests", unit: "per_service" },
  { slug: "botox-per-unit", name: "Botox (per unit)", category: "Cosmetic", unit: "per_unit" },
  { slug: "dermal-filler-per-syringe", name: "Dermal filler (per syringe)", category: "Cosmetic", unit: "per_syringe" },
  { slug: "weight-loss-program-monthly", name: "Medical weight-loss program (per month)", category: "Weight loss", unit: "per_month" },
  { slug: "teeth-cleaning-adult", name: "Teeth cleaning (adult)", category: "Dental", unit: "per_visit" },
];

const SYNONYMS: [string, string][] = [
  ["mri-brain-without-contrast", "head mri"],
  ["mri-lower-back-without-contrast", "back mri"],
  ["colonoscopy-diagnostic", "scope"],
  ["teeth-cleaning-adult", "dentist cleaning"],
  ["botox-per-unit", "wrinkle injection"],
  ["complete-blood-count", "blood work"],
  ["weight-loss-program-monthly", "semaglutide program"],
];

export const DEMO_PROVIDER_TYPES: ProviderType[] = [
  { code: "hospital", name: "Hospital" },
  { code: "surgery_center", name: "Surgery center" },
  { code: "imaging_center", name: "Imaging center" },
  { code: "dental_office", name: "Dental office" },
  { code: "medical_spa", name: "Medical spa" },
];

export const DEMO_PLANS: Plan[] = [
  { plan_id: "00000000-0000-4000-8000-000000000001", payer: "Sample Health", plan: "Sample Health PPO", product_type: "ppo", segment: "commercial" },
  { plan_id: "00000000-0000-4000-8000-000000000002", payer: "Sample Care", plan: "Sample Care HMO", product_type: "hmo", segment: "commercial" },
  { plan_id: "00000000-0000-4000-8000-000000000003", payer: "Sample Health", plan: "Sample Health EPO", product_type: "epo", segment: "commercial" },
];
const ALL_PLANS: Plan = { plan_id: "-", payer: "Sample Health", plan: "All Plans", product_type: "unknown", segment: "commercial" };

interface DemoFacility {
  id: string;
  name: string;
  city: string;
  miles: string;
  types: string[];
  factor: [bigint, bigint]; // cash = base * a / b
  published: string | null;
}

const FACILITIES: DemoFacility[] = [
  { id: "d0000000-0000-4000-8000-000000000001", name: "Sample Valley Hospital", city: "Las Vegas", miles: "1.2", types: ["hospital"], factor: [140n, 100n], published: "2026-10-01" },
  { id: "d0000000-0000-4000-8000-000000000002", name: "Sample Surgery Center", city: "Henderson", miles: "4.8", types: ["surgery_center"], factor: [62n, 100n], published: "2026-10-15" },
  { id: "d0000000-0000-4000-8000-000000000003", name: "Sample Imaging Clinic", city: "Las Vegas", miles: "3.1", types: ["imaging_center"], factor: [48n, 100n], published: "2026-09-20" },
  { id: "d0000000-0000-4000-8000-000000000004", name: "Sample Desert Medical Center", city: "Las Vegas", miles: "6.4", types: ["hospital"], factor: [210n, 100n], published: "2026-08-30" },
  { id: "d0000000-0000-4000-8000-000000000005", name: "Sample Lakes Hospital", city: "North Las Vegas", miles: "9.7", types: ["hospital"], factor: [118n, 100n], published: "2026-10-05" },
  { id: "d0000000-0000-4000-8000-000000000006", name: "Sample Family Dental", city: "Las Vegas", miles: "2.2", types: ["dental_office"], factor: [100n, 100n], published: "2026-11-01" },
  { id: "d0000000-0000-4000-8000-000000000007", name: "Sample Glow Med Spa", city: "Summerlin", miles: "7.5", types: ["medical_spa"], factor: [100n, 100n], published: "2026-11-02" },
  { id: "d0000000-0000-4000-8000-000000000008", name: "Sample Community Hospital", city: "Boulder City", miles: "18.9", types: ["hospital"], factor: [100n, 100n], published: null },
];

// base cash price in whole dollars and a made-up code per sample service
const BASE: Record<string, [bigint, string]> = {
  "mri-brain-without-contrast": [900n, "CPT 70551"],
  "mri-lower-back-without-contrast": [850n, "CPT 72148"],
  "mri-knee-without-contrast": [780n, "CPT 73721"],
  "ct-head-without-contrast": [420n, "CPT 70450"],
  "chest-x-ray-two-views": [95n, "CPT 71046"],
  "colonoscopy-diagnostic": [1650n, "CPT 45378"],
  "cataract-surgery": [2900n, "CPT 66984"],
  "knee-arthroscopy-meniscus": [4100n, "CPT 29881"],
  "blood-panel-comprehensive": [38n, "CPT 80053"],
  "complete-blood-count": [24n, "CPT 85025"],
  "cholesterol-panel": [32n, "CPT 80061"],
  ekg: [65n, "CPT 93000"],
  "botox-per-unit": [12n, "provider-entered"],
  "dermal-filler-per-syringe": [650n, "provider-entered"],
  "weight-loss-program-monthly": [299n, "provider-entered"],
  "teeth-cleaning-adult": [115n, "CDT D1110"],
};

function offers(f: DemoFacility, slug: string): boolean {
  const cat = DEMO_SERVICES.find((s) => s.slug === slug)?.category;
  if (f.types.includes("dental_office")) return cat === "Dental";
  if (f.types.includes("medical_spa")) return cat === "Cosmetic" || cat === "Weight loss";
  if (cat === "Dental" || cat === "Cosmetic" || cat === "Weight loss") return false;
  if (f.types.includes("imaging_center")) return cat === "Imaging";
  if (f.types.includes("surgery_center")) return cat === "Surgery" || cat === "Procedures";
  return true;
}

const s = (n: bigint) => n.toString();

function pricesFor(f: DemoFacility, slug: string): Price[] {
  const [base, code] = BASE[slug] ?? [100n, "CPT 00000"];
  const cash = (base * f.factor[0]) / f.factor[1];
  const list = cash * 3n;
  const provider = f.types.includes("dental_office") || f.types.includes("medical_spa");
  const src = provider ? "provider_entered" : "hospital_file";
  const row = (price_type: string, amount: bigint, plan: Plan | null): Price => ({
    price_source: src,
    code,
    description: "Sample item",
    setting: "outpatient",
    price_type,
    payer: plan?.payer ?? null,
    plan: plan?.plan ?? null,
    amount: s(amount),
    percentage: null,
    algorithm: null,
    methodology: price_type === "negotiated" ? "fee schedule" : null,
  });
  const out = [row("discounted_cash", cash, null)];
  if (!provider) {
    out.push(row("gross", list, null));
    out.push(row("negotiated", (cash * 105n) / 100n, DEMO_PLANS[0]!));
    out.push(row("negotiated", (cash * 88n) / 100n, DEMO_PLANS[1]!));
    out.push(row("negotiated", (cash * 98n) / 100n, ALL_PLANS));
  }
  return out;
}

export function demoSuggest(q: string): Suggestion[] {
  const n = q.trim().toLowerCase();
  if (n.length < 2) return [];
  const out: Suggestion[] = [];
  for (const [slug, [, code]] of Object.entries(BASE)) {
    const [system, num] = code.split(" ");
    if (num && /\d/.test(n) && num.toLowerCase().startsWith(n)) {
      const svc = DEMO_SERVICES.find((s) => s.slug === slug)!;
      out.push({ slug: `code:${system}:${num}`, name: `${svc.name} (sample hospital wording)`, unit: "per_service", matched: code, kind: "code", code_system: system!, code: num });
    }
  }
  for (const svc of DEMO_SERVICES) {
    const syn = SYNONYMS.find(([slug, term]) => slug === svc.slug && term.includes(n));
    if (svc.name.toLowerCase().includes(n)) out.push({ ...svc, matched: svc.name });
    else if (syn) out.push({ ...svc, matched: syn[1] });
  }
  return out.slice(0, 8);
}

export function demoPlace(zip: string): Place | null {
  return /^\d{5}$/.test(zip) ? { zip, state: "NV", lat: "36.17", lng: "-115.14" } : null;
}

export function demoSearch(slug: string, mode: Mode, planId: string | null, providerType: string | null, radius = "25"): SearchResult {
  const svc = DEMO_SERVICES.find((x) => x.slug === slug) ?? DEMO_SERVICES[0]!;
  const plan = DEMO_PLANS.find((p) => p.plan_id === planId) ?? null;
  const wanted = mode === "cash" ? "discounted_cash" : mode === "list" ? "gross" : "negotiated";
  const near = FACILITIES.filter((f) => offers(f, svc.slug) || f.published === null)
    .filter((f) => Number(f.miles) <= Number(radius))
    .filter(
    (f) => {
      // a comma list of kinds of care, like the real search (Cooper, 2026-11-12)
      const kinds = (providerType ?? "").split(",").filter(Boolean);
      return kinds.length === 0 || kinds.some((k) => f.types.includes(k));
    },
  );
  const rows: Facility[] = near.map((f) => {
    const prices = f.published ? pricesFor(f, svc.slug) : [];
    const neg = prices.filter((p) => p.price_type === "negotiated");
    const exact = neg.filter((p) => p.plan === plan?.plan).map((p) => ({ ...p, plan_match: "plan" as const }));
    const canFallBack = !!plan && plan.segment === "commercial" && ["hmo", "ppo", "epo", "pos"].includes(plan.product_type);
    const fallback = canFallBack
      ? neg.filter((p) => p.payer === plan!.payer && p.plan === ALL_PLANS.plan).map((p) => ({ ...p, plan_match: "all_plans" as const }))
      : [];
    const pool = mode === "plan" ? (exact.length ? exact : fallback) : [];
    const allPlans = mode === "plan" && exact.length === 0 && fallback.length > 0;
    const shown = [...prices.filter((p) => p.price_type !== "negotiated"), ...pool];
    const head = shown.find((p) => p.price_type === wanted);
    const cash = shown.find((p) => p.price_type === "discounted_cash");
    return {
      facility_id: f.id,
      name: f.name,
      city: f.city,
      state: "NV",
      distance_miles: f.miles,
      provider_types: f.types,
      status: prices.length ? "prices" : "no_published_prices",
      prices_published_at: f.published,
      headline: head?.amount ?? null,
      headline_highest: null,
      headline_price_type: head?.price_type ?? null,
      headline_possible_error: false,
      lowest_near_you: false,
      below_typical: false,
      cash_cheaper_than_plan: !!(mode === "plan" && head && cash && BigInt(cash.amount!) < BigInt(head.amount!)),
      badge_notes: [],
      change_percent_since_last_file: f.id.endsWith("1") ? "-8.0" : null,
      plan_rate_is_all_plans: allPlans,
      special:
        mode === "cash" && f.types.includes("dental_office") && head
          ? { price: s((BigInt(head.amount!) * 70n) / 100n), who: "new_patients", ends_on: "2026-12-31", terms: "Sample special" }
          : mode === "cash" && f.types.includes("medical_spa") && head
            ? { price: s((BigInt(head.amount!) * 80n) / 100n), who: "everyone", ends_on: null, terms: null }
            : null,
      prices: shown,
    };
  });
  const amounts = rows.filter((r) => r.headline).map((r) => BigInt(r.headline!)).sort((a, b) => (a < b ? -1 : 1));
  const lowest = amounts[0];
  for (const r of rows) r.lowest_near_you = r.headline !== null && amounts.length > 1 && BigInt(r.headline) === lowest;
  let typical: SearchResult["typical"] = null;
  if (amounts.length >= 5) {
    const rank = (p: number) => amounts[Math.max(0, Math.ceil((p / 100) * amounts.length) - 1)]!;
    typical = { low: s(rank(25)), middle: s(rank(50)), high: s(rank(75)), count: amounts.length };
    for (const r of rows) r.below_typical = r.headline !== null && BigInt(r.headline) < BigInt(typical.low);
  }
  rows.sort((a, b) => {
    if (!a.headline || !b.headline) return a.headline ? -1 : b.headline ? 1 : 0;
    return BigInt(a.headline) < BigInt(b.headline) ? -1 : 1;
  });
  const code = BASE[svc.slug]?.[1];
  return {
    service: svc.slug,
    service_name: svc.name,
    unit: svc.unit,
    codes: code && code !== "provider-entered" ? [code] : [],
    note: null,
    mode,
    typical,
    facilities: rows,
  };
}

export function demoNearby(): NearbyFacility[] {
  return FACILITIES.filter((f) => f.types.includes("hospital")).map((f) => ({
    facility_id: f.id,
    name: f.name,
    city: f.city,
    state: "NV",
    distance_miles: f.miles,
    provider_types: f.types,
  }));
}

// HHS 2026 poverty guidelines (48 states + DC), the same public figures as
// data/reference/poverty_guidelines.csv; the hospital policies below are samples.
const guideline = (size: number) => 15960n + 5680n * BigInt(size - 1);
const fmt = (n: bigint) => "$" + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");

export function demoMessage(): AssistanceMessage {
  return {
    message: `At many hospitals you may qualify for free care if your household makes under ${fmt(guideline(1) * 2n)} (1 person) or ${fmt(guideline(4) * 2n)} (family of 4).`,
    detail:
      "Nonprofit hospitals are required by federal law to have a written financial assistance policy, and many other hospitals offer one. Each hospital sets its own rules. Only the hospital can confirm what you will receive.",
  };
}

export function demoCheck(size: number, income: string): AssistanceCheck {
  const g = guideline(size);
  const cents = BigInt(income.split(".")[0] || "0") * 100n; // whole dollars of a typed income
  const pct = (cents * 100n) / (g * 100n);
  const policies: Record<string, [bigint, bigint]> = {
    "d0000000-0000-4000-8000-000000000001": [200n, 400n],
    "d0000000-0000-4000-8000-000000000004": [250n, 400n],
    "d0000000-0000-4000-8000-000000000005": [200n, 300n],
  };
  return {
    message: "",
    coverage: demoCoverage(size, pct),
    guideline_year: 2026,
    guideline_amount: s(g),
    income_percent_of_guideline: s(pct),
    reminder: "Only the hospital can confirm what you will receive. Apply even if unsure.",
    facilities: demoNearby().map((f) => {
      const p = policies[f.facility_id];
      if (!p) {
        return { facility_id: f.facility_id, name: f.name, status: "policy_not_reviewed", best: null, policy_url: null, application_url: null, phone: null, message: `Ask ${f.name} about financial assistance.` };
      }
      const [free, disc] = p;
      const status = pct <= free ? "may_qualify_free" : pct <= disc ? "may_qualify_discount" : "above_published_limits";
      return {
        facility_id: f.facility_id,
        name: f.name,
        status,
        best: status === "above_published_limits" ? null : { benefit: status === "may_qualify_free" ? "free" : "discount", up_to_percent_of_poverty_guideline: s(status === "may_qualify_free" ? free : disc), discount_percent: status === "may_qualify_free" ? null : "60", description: null },
        policy_url: "#sample",
        application_url: "#sample",
        phone: "(000) 555-0100",
        message: `Free care under ${fmt((g * free) / 100n)} for your household size; discounts up to ${fmt((g * disc) / 100n)}.`,
      };
    }),
  };
}

export function demoFacility(id: string): FacilityDetail | null {
  const f = FACILITIES.find((x) => x.id === id);
  if (!f) return null;
  return {
    facility_id: f.id,
    name: f.name,
    address: "100 Sample Street",
    city: f.city,
    state: "NV",
    zip: "89101",
    phone: "(000) 555-0100",
    website: null,
    emergency_services: f.types.includes("hospital"),
    cms_rating: null,
    cms_rating_as_of: null,
    provider_types: f.types,
    prices_published_at: f.published,
    lat: "36.17",
    lng: "-115.14",
  };
}

export function demoFacilityPrices(id: string, slug: string): FacilityPrices {
  const f = FACILITIES.find((x) => x.id === id) ?? FACILITIES[0]!;
  const svc = DEMO_SERVICES.find((x) => x.slug === slug) ?? DEMO_SERVICES[0]!;
  const code = BASE[svc.slug]?.[1];
  return {
    facility_id: f.id,
    service: svc.slug,
    service_name: svc.name,
    unit: svc.unit,
    codes: code && code !== "provider-entered" ? [code] : [],
    prices_published_at: f.published,
    prices: f.published && offers(f, svc.slug) ? pricesFor(f, svc.slug) : [],
  };
}

export function demoFacilityAssistance(id: string): { facility_id: string; message: string } {
  const f = FACILITIES.find((x) => x.id === id);
  const sample = ["d0000000-0000-4000-8000-000000000001", "d0000000-0000-4000-8000-000000000004", "d0000000-0000-4000-8000-000000000005"];
  return {
    facility_id: id,
    message: f && sample.includes(id)
      ? `You may qualify for free care at ${f.name} if your household makes under ${fmt(guideline(1) * 2n)} (1 person) or ${fmt(guideline(4) * 2n)} (family of 4). Discounts may be available up to ${fmt(guideline(1) * 4n)} (1 person) or ${fmt(guideline(4) * 4n)} (family of 4).`
      : `Ask ${f?.name ?? "this facility"} about financial assistance; we have not reviewed its policy yet.`,
  };
}

// Sample bundles shaped like data/reference/bundles.csv (made-up prices).
export const DEMO_BUNDLES: Bundle[] = [
  {
    slug: "colonoscopy-complete",
    name: "Colonoscopy, everything included",
    components: [
      { component_id: "c1", label: "Colonoscopy (the procedure and facility)", role: "procedure", requirement: "required", included_by_default: true, code: "CPT 45378", notes: "facility and doctor both bill this code" },
      { component_id: "c2", label: "Anesthesia", role: "anesthesia", requirement: "optional", included_by_default: true, code: "CPT 00811", notes: "often billed by a separate anesthesia group" },
      { component_id: "c3", label: "Biopsy lab review (if a sample is taken)", role: "pathology", requirement: "optional", included_by_default: false, code: "CPT 88305", notes: "only if a tissue sample is taken" },
    ],
  },
  {
    slug: "vaginal-birth-complete",
    name: "Vaginal birth, everything included",
    components: [
      { component_id: "b1", label: "Hospital stay for the birth", role: "facility", requirement: "required", included_by_default: true, code: "MS-DRG 807", notes: "vaginal delivery without major complications" },
      { component_id: "b2", label: "Doctor's care (prenatal visits, delivery and follow-up)", role: "physician", requirement: "required", included_by_default: true, code: "CPT 59400", notes: "global obstetric care" },
      { component_id: "b3", label: "Epidural", role: "anesthesia", requirement: "optional", included_by_default: false, code: "CPT 01967", notes: "labor epidural" },
      { component_id: "b4", label: "Newborn hospital care", role: "newborn", requirement: "optional", included_by_default: true, code: "MS-DRG 795", notes: "normal newborn stay" },
    ],
  },
];

const BUNDLE_PRICES: Record<string, bigint | null> = { c1: 1650n, c2: null, c3: 95n, b1: 9800n, b2: null, b3: 1400n, b4: 2100n };

export function demoEstimate(slug: string, facilityId: string, payment: "cash" | "list", include: string[]): Estimate {
  const b = DEMO_BUNDLES.find((x) => x.slug === slug) ?? DEMO_BUNDLES[0]!;
  const f = FACILITIES.find((x) => x.id === facilityId) ?? FACILITIES[0]!;
  const lines = b.components.map((c) => {
    const included = c.requirement === "required" || include.includes(c.component_id);
    const base = BUNDLE_PRICES[c.component_id] ?? null;
    const amount = base === null ? null : ((base * f.factor[0]) / f.factor[1]) * (payment === "list" ? 3n : 1n);
    return {
      component_id: c.component_id,
      label: c.label,
      role: c.role,
      requirement: c.requirement,
      included,
      status: !included ? "left_out" : amount === null ? "not_published" : "priced",
      amount: included && amount !== null ? s(amount) : null,
      amounts_published: [],
      rate: null,
      notes: c.notes,
    };
  });
  const priced = lines.filter((l) => l.status === "priced").map((l) => BigInt(l.amount!));
  const complete = lines.filter((l) => l.included).every((l) => l.status === "priced");
  return {
    bundle: b.slug,
    name: b.name,
    facility_id: f.id,
    payment,
    payer: null,
    plan: null,
    lines,
    total_of_priced_pieces: priced.length ? s(priced.reduce((a, x) => a + x, 0n)) : null,
    complete,
    explanation: complete
      ? "Every included piece has a published price."
      : "Some included pieces have no published dollar price here (often doctors' or anesthesia fees billed separately); the total covers only the priced pieces.",
  };
}

// Sample cities for the service-by-city pages (centers are rough, made-up points).
export const DEMO_CITIES = [
  { state: "NV", city: "Las Vegas", slug: "las-vegas", lat: "36.17", lng: "-115.14", facilities: 4 },
  { state: "NV", city: "Henderson", slug: "henderson", lat: "36.04", lng: "-114.98", facilities: 1 },
  { state: "NV", city: "North Las Vegas", slug: "north-las-vegas", lat: "36.20", lng: "-115.12", facilities: 1 },
  { state: "NV", city: "Summerlin", slug: "summerlin", lat: "36.18", lng: "-115.33", facilities: 1 },
  { state: "NV", city: "Boulder City", slug: "boulder-city", lat: "35.98", lng: "-114.83", facilities: 1 },
];

// Same percentages as data/reference/coverage_limits.csv, shown only in preview.
function demoCoverage(size: number, pct: bigint) {
  const g = guideline(size);
  const people = size === 1 ? "person" : "people";
  const rows: [string, string, string, bigint, bigint][] = [
    ["medicaid", "adults", "Nevada Medicaid (adults 19 to 64)", 0n, 138n],
    ["medicaid", "children", "Nevada Medicaid or Nevada Check Up (children under 19)", 0n, 205n],
    ["medicaid", "pregnant", "Nevada Medicaid for pregnancy", 0n, 205n],
    ["marketplace_savings", "everyone", "Lower-cost marketplace insurance (premium tax credit)", 138n, 400n],
  ];
  return rows
    .filter(([, , , lo, hi]) => pct >= lo && pct <= hi)
    .map(([program, group, label, lo, hi]) => ({
      program,
      group,
      label,
      limit: lo > 0n ? `about ${fmt((g * lo) / 100n)} to ${fmt((g * hi) / 100n)} a year for ${size} ${people}` : `up to about ${fmt((g * hi) / 100n)} a year for ${size} ${people}`,
      apply_url: "https://www.nevadahealthlink.com/",
      source_url: "#sample",
    }));
}

export function demoHealthCenters() {
  return [
    { name: "Sample Community Health Center", organization: "Sample Health Org", address: "200 Sample Ave", city: "Las Vegas", state: "NV", zip: "89101", phone: "(000) 555-0123", website: null, distance_miles: "1.8" },
    { name: "Sample Family Health Clinic", organization: "Sample Health Org", address: "45 Example Blvd", city: "North Las Vegas", state: "NV", zip: "89030", phone: "(000) 555-0124", website: null, distance_miles: "5.2" },
  ];
}

// Preview only: a code search maps back to the sample service with that code.
export function demoServiceForCode(code: string): string {
  const hit = Object.entries(BASE).find(([, [, c]]) => c.endsWith(" " + code));
  return hit ? hit[0] : DEMO_SERVICES[0]!.slug;
}

export function demoPayerSuggest(q: string) {
  const names = ["SAMPLE HEALTH", "Sample Health All Plans", "SAMPLE CARE HMO", "Sample Union Trust"];
  const n = q.trim().toLowerCase();
  return names.filter((x) => x.toLowerCase().includes(n)).map((name, i) => ({ name, facilities: 4 - i }));
}

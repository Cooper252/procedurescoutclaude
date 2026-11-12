// One place for every call to the ProcedureScout API. In preview mode (no
// API configured) the same functions answer from lib/synthetic_demo.ts.

import * as demo from "./synthetic_demo";
import type {
  Bundle,
  Estimate,
  FacilityDetail,
  FacilityPrices,
  HealthCenter,
  AssistanceCheck,
  AssistanceMessage,
  Mode,
  NearbyFacility,
  Place,
  Plan,
  ProviderType,
  SearchResult,
  Service,
  Suggestion,
} from "./types";

export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function get<T>(path: string, params?: Record<string, string | null | undefined>): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v != null && v !== "") qs.set(k, v);
  const res = await fetch(`/api${path}${qs.size ? "?" + qs.toString() : ""}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new ApiError(await detail(res), res.status);
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(await detail(res), res.status);
  return (await res.json()) as T;
}

async function detail(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    return typeof j.detail === "string" ? j.detail : `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

const later = <T,>(v: T) => new Promise<T>((r) => setTimeout(() => r(v), 120));

export const api = {
  services: (): Promise<Service[]> => (DEMO ? later(demo.DEMO_SERVICES) : get("/v1/services")),
  suggest: (q: string): Promise<Suggestion[]> =>
    DEMO ? later(demo.demoSuggest(q)) : get("/v1/services/suggest", { q }),
  providerTypes: (): Promise<ProviderType[]> =>
    DEMO ? later(demo.DEMO_PROVIDER_TYPES) : get("/v1/provider-types"),
  plans: (): Promise<Plan[]> => (DEMO ? later(demo.DEMO_PLANS) : get("/v1/plans")),
  zip: async (zip: string): Promise<Place> => {
    if (!DEMO) return get(`/v1/places/zip/${encodeURIComponent(zip)}`);
    const p = demo.demoPlace(zip);
    if (!p) throw new ApiError("ZIP code not found", 404);
    return later(p);
  },
  search: (p: {
    lat: string;
    lng: string;
    service: string;
    codeSystem?: string | null;
    code?: string | null;
    mode: Mode;
    planId?: string | null;
    payerRaw?: string | null;
    providerType?: string | null;
    radius?: string;
    online?: boolean;
  }): Promise<SearchResult> =>
    DEMO
      ? later({ ...demo.demoSearch(p.code ? demo.demoServiceForCode(p.code) : p.service, p.mode, p.planId ?? null, p.providerType ?? null, p.radius ?? "25"), code_description: p.code ? "Sample hospital wording for this code" : null })
      : get("/v1/search", {
          lat: p.lat,
          lng: p.lng,
          service: p.code ? null : p.service,
          code_system: p.code ? p.codeSystem : null,
          code: p.code,
          mode: p.mode,
          plan_id: p.mode === "plan" ? p.planId : null,
          payer: p.mode === "plan" && !p.planId ? p.payerRaw : null,
          provider_type: p.providerType,
          radius_miles: p.radius ?? "25",
          online: p.online ? "true" : null,
        }),
  nearby: (lat: string, lng: string): Promise<NearbyFacility[]> =>
    DEMO ? later(demo.demoNearby()) : get("/v1/facilities/near", { lat, lng, provider_type: "hospital" }),
  message: (state: string | null): Promise<AssistanceMessage> =>
    DEMO ? later(demo.demoMessage()) : get("/v1/assistance/message", { state }),
  check: (b: {
    facilityIds: string[];
    householdSize: number;
    income: string;
    state: string;
  }): Promise<AssistanceCheck> =>
    DEMO
      ? later(demo.demoCheck(b.householdSize, b.income))
      : post("/v1/assistance/check", {
          facility_ids: b.facilityIds,
          household_size: b.householdSize,
          annual_income: b.income,
          state: b.state,
        }),
  facility: (id: string): Promise<FacilityDetail> => {
    if (!DEMO) return get(`/v1/facilities/${encodeURIComponent(id)}`);
    const f = demo.demoFacility(id);
    if (!f) return Promise.reject(new ApiError("unknown facility", 404));
    return later(f);
  },
  facilityPrices: (id: string, service: string): Promise<FacilityPrices> =>
    DEMO
      ? later(demo.demoFacilityPrices(id, service))
      : get(`/v1/facilities/${encodeURIComponent(id)}/prices`, { service }),
  facilityAssistance: (id: string, state: string): Promise<{ facility_id: string; message: string }> =>
    DEMO
      ? later(demo.demoFacilityAssistance(id))
      : get(`/v1/facilities/${encodeURIComponent(id)}/assistance`, { state }),
  payerSuggest: (q: string): Promise<{ name: string; facilities: number }[]> =>
    DEMO ? later(demo.demoPayerSuggest(q)) : get("/v1/payers/suggest", { q }),
  healthCenters: (lat: string, lng: string): Promise<HealthCenter[]> =>
    DEMO ? later(demo.demoHealthCenters()) : get("/v1/health-centers/near", { lat, lng }),
  bundles: (): Promise<Bundle[]> => (DEMO ? later(demo.DEMO_BUNDLES) : get("/v1/bundles")),
  estimate: (
    slug: string,
    b: { facilityId: string; payment: "cash" | "list"; includeOptional: string[] },
  ): Promise<Estimate> =>
    DEMO
      ? later(demo.demoEstimate(slug, b.facilityId, b.payment, b.includeOptional))
      : post(`/v1/bundles/${encodeURIComponent(slug)}/estimate`, {
          facility_id: b.facilityId,
          payment: b.payment,
          include_optional: b.includeOptional,
        }),
};

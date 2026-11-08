// Shapes returned by the ProcedureScout API (docs/API_CONTRACTS.md).
// Amounts are exact decimal strings.

export type Mode = "cash" | "list" | "plan";

export interface Service {
  slug: string;
  name: string;
  category: string | null;
  unit: string;
}

export interface Suggestion {
  slug: string;
  name: string;
  unit: string;
  matched: string;
  kind?: "service" | "code";
  code_system?: string | null;
  code?: string | null;
}

export interface ProviderType {
  code: string;
  name: string;
}

export interface Plan {
  plan_id: string;
  payer: string;
  plan: string;
  product_type: string;
  segment: string;
}

export interface Place {
  zip: string;
  state: string;
  lat: string;
  lng: string;
}

export interface Price {
  price_source: string;
  code: string;
  description: string | null;
  setting: string | null;
  price_type: string;
  payer: string | null;
  plan: string | null;
  amount: string | null;
  percentage: string | null;
  algorithm: string | null;
  methodology: string | null;
  plan_match?: "plan" | "all_plans" | null;
}

export interface Facility {
  facility_id: string;
  name: string;
  city: string | null;
  state: string;
  distance_miles: string;
  provider_types: string[];
  status: "prices" | "no_published_prices" | string;
  prices_published_at: string | null;
  headline: string | null;
  headline_highest: string | null;
  headline_price_type: string | null;
  headline_possible_error: boolean;
  lowest_near_you: boolean;
  below_typical: boolean;
  cash_cheaper_than_plan: boolean;
  badge_notes: string[];
  change_percent_since_last_file: string | null;
  plan_rate_is_all_plans?: boolean;
  special?: { price: string; who: "new_patients" | "everyone"; ends_on: string | null; terms: string | null } | null;
  prices: Price[];
}

export interface SearchResult {
  service: string | null;
  service_name: string | null;
  unit: string | null;
  codes: string[];
  note: string | null;
  mode: Mode;
  code_description?: string | null;
  typical: { low: string; middle: string; high: string; count: number } | null;
  facilities: Facility[];
}

export interface NearbyFacility {
  facility_id: string;
  name: string;
  city: string | null;
  state: string;
  distance_miles: string;
  provider_types: string[];
}

export interface AssistanceMessage {
  message: string;
  detail: string;
}

export interface AssistanceFacility {
  facility_id: string;
  name: string;
  status: string; // may_qualify_free | may_qualify_discount | above_published_limits | policy_not_reviewed
  best: {
    benefit: string;
    up_to_percent_of_poverty_guideline: string;
    discount_percent: string | null;
    description: string | null;
  } | null;
  policy_url: string | null;
  application_url: string | null;
  phone: string | null;
  message: string;
}

export interface CoverageItem {
  program: string;
  group: string;
  label: string;
  limit: string;
  apply_url: string;
  source_url: string;
}

export interface HealthCenter {
  name: string;
  organization: string | null;
  address: string | null;
  city: string | null;
  state: string;
  zip: string | null;
  phone: string | null;
  website: string | null;
  distance_miles: string;
}

export interface AssistanceCheck {
  coverage?: CoverageItem[];
  message: string;
  guideline_year: number;
  guideline_amount: string;
  income_percent_of_guideline: string;
  facilities: AssistanceFacility[];
  reminder: string;
}

export interface FacilityDetail {
  facility_id: string;
  name: string;
  address: string | null;
  city: string | null;
  state: string;
  zip: string | null;
  phone: string | null;
  website: string | null;
  emergency_services: boolean | null;
  cms_rating: number | null;
  cms_rating_as_of: string | null;
  provider_types: string[];
  prices_published_at: string | null;
  lat: string | null;
  lng: string | null;
}

export interface FacilityPrices {
  facility_id: string;
  service: string;
  service_name: string;
  unit: string;
  codes: string[];
  prices_published_at: string | null;
  prices: Price[];
}

export interface BundleComponent {
  component_id: string;
  label: string;
  role: string;
  requirement: "required" | "optional" | string;
  included_by_default: boolean;
  code: string;
  notes: string | null;
}

export interface Bundle {
  slug: string;
  name: string;
  components: BundleComponent[];
}

export interface EstimateLine {
  component_id: string;
  label: string;
  role: string;
  requirement: string;
  included: boolean;
  status: string; // priced | not_published | not_a_dollar_amount | several_prices | left_out
  amount: string | null;
  amounts_published: string[];
  rate: string | null;
  notes: string | null;
}

export interface Estimate {
  bundle: string;
  name: string;
  facility_id: string;
  payment: "cash" | "list" | "insurance";
  payer: string | null;
  plan: string | null;
  lines: EstimateLine[];
  total_of_priced_pieces: string | null;
  complete: boolean;
  explanation: string;
}

// Money arrives from the API as exact decimal strings ("100.1", "2450").
// It is formatted with string and BigInt arithmetic only: never parseFloat,
// so a published price is never changed by floating point.

const DECIMAL = /^-?\d+(\.\d+)?$/;

/** "$1,250" or "$100.10"; amounts with more than 2 decimals are shown to the
 *  cent and flagged as rounded so the page can say so. */
export function formatMoney(value: string | null | undefined): { text: string; rounded: boolean } | null {
  if (value == null || !DECIMAL.test(value)) return null;
  const negative = value.startsWith("-");
  const [whole = "0", frac = ""] = value.replace("-", "").split(".");
  let cents = BigInt(whole) * 100n + BigInt((frac + "00").slice(0, 2));
  const rest = frac.slice(2);
  const rounded = /[1-9]/.test(rest);
  if (rounded && Number(rest[0]) >= 5) cents += 1n; // half-up, display only
  const dollars = (cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const c = (cents % 100n).toString().padStart(2, "0");
  const text = `${negative ? "-" : ""}$${dollars}${c === "00" && !rounded ? "" : "." + c}`;
  return { text, rounded };
}

export function money(value: string | null | undefined): string {
  return formatMoney(value)?.text ?? "—";
}

/** Whole dollars typed by a person ("52,000" or "$52000") as a plain digit string. */
export function cleanIncome(input: string): string | null {
  const digits = input.replace(/[$,\s]/g, "");
  return /^\d{1,9}(\.\d{1,2})?$/.test(digits) ? digits : null;
}

export function unitLabel(unit: string | null | undefined, lang: "en" | "es"): string {
  const en: Record<string, string> = {
    per_service: "per procedure",
    per_unit: "per unit",
    per_syringe: "per syringe",
    per_month: "per month",
    per_visit: "per visit",
    per_session: "per session",
    per_area: "per area",
    per_day: "per day",
    per_tooth: "per tooth",
    per_quadrant: "per quarter of the mouth",
    per_arch: "per arch (upper or lower)",
    per_eye: "per eye",
    per_vial: "per vial",
    per_injection: "per shot",
  };
  const es: Record<string, string> = {
    per_service: "por procedimiento",
    per_unit: "por unidad",
    per_syringe: "por jeringa",
    per_month: "por mes",
    per_visit: "por visita",
    per_session: "por sesión",
    per_area: "por área",
    per_day: "por día",
    per_tooth: "por diente",
    per_quadrant: "por cuarto de la boca",
    per_arch: "por arcada (superior o inferior)",
    per_eye: "por ojo",
    per_vial: "por frasco",
    per_injection: "por inyección",
  };
  return (lang === "es" ? es : en)[unit ?? ""] ?? "";
}

/** Compare two exact non-negative decimal strings without floating point. */
export function compareDecimal(a: string, b: string): number {
  const [ai = "0", af = ""] = a.split(".");
  const [bi = "0", bf = ""] = b.split(".");
  const n = Math.max(af.length, bf.length);
  const x = BigInt(ai + af.padEnd(n, "0"));
  const y = BigInt(bi + bf.padEnd(n, "0"));
  return x < y ? -1 : x > y ? 1 : 0;
}

/** a - b for exact decimal strings (b <= a), without floating point. */
export function subtractDecimal(a: string, b: string): string {
  const [ai = "0", af = ""] = a.split(".");
  const [bi = "0", bf = ""] = b.split(".");
  const n = Math.max(af.length, bf.length);
  const d = BigInt(ai + af.padEnd(n, "0")) - BigInt(bi + bf.padEnd(n, "0"));
  if (n === 0) return d.toString();
  const s = d.toString().padStart(n + 1, "0");
  return `${s.slice(0, -n)}.${s.slice(-n)}`;
}

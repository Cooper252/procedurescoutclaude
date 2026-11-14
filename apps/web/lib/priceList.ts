// The à la carte price list (Cooper, 2026-11-14): a person ticks the pieces
// they need (a hospital stay, anesthesia, the doctor, newborn care...) and
// sees, for each place, every piece's price and the total of those prices.
// A total is shown only when the place published a dollar price for every
// piece; amounts are added exactly as published (no rounding, no floats).

export type Item = { kind: "service"; slug: string } | { kind: "code"; system: string; code: string };

/** "svc:<slug>" or "<SYSTEM>:<code>" (the first ":" separates them) */
export function parseItem(key: string): Item | null {
  const i = key.indexOf(":");
  if (i <= 0 || i === key.length - 1) return null;
  const a = key.slice(0, i);
  const b = key.slice(i + 1);
  return a === "svc" ? { kind: "service", slug: b } : { kind: "code", system: a, code: b };
}

/** one item's own price search */
export function itemHref(key: string, rest: URLSearchParams): string | null {
  const it = parseItem(key);
  if (!it) return null;
  const p = new URLSearchParams(rest.toString());
  p.delete("q");
  p.delete("i");
  p.delete("add");
  if (it.kind === "service") p.set("service", it.slug);
  else {
    p.set("code_system", it.system);
    p.set("code", it.code);
  }
  return `/search?${p.toString()}`;
}

/** the price list for several items */
export function listHref(keys: string[], rest: URLSearchParams): string {
  const p = new URLSearchParams(rest.toString());
  p.delete("i");
  p.delete("add");
  p.delete("service");
  p.delete("code_system");
  p.delete("code");
  for (const k of keys) p.append("i", k);
  return `/price-list?${p.toString()}`;
}

const DEC = /^-?\d+(\.\d+)?$/;

/** exact sum of published decimal amounts; null if any is not a plain number */
export function addDecimals(values: string[]): string | null {
  if (!values.length || values.some((v) => !DEC.test(v))) return null;
  const scale = Math.max(...values.map((v) => (v.split(".")[1] ?? "").length));
  let total = 0n;
  for (const v of values) {
    const neg = v.startsWith("-");
    const [w = "0", f = ""] = (neg ? v.slice(1) : v).split(".");
    const n = BigInt(w + f.padEnd(scale, "0"));
    total += neg ? -n : n;
  }
  const neg = total < 0n;
  const s = (neg ? -total : total).toString().padStart(scale + 1, "0");
  const out = scale ? `${s.slice(0, s.length - scale)}.${s.slice(s.length - scale)}` : s;
  return neg ? `-${out}` : out;
}

export type Line = { key: string; low: string | null; high: string | null; ratesOnly?: boolean; pricedAs?: string[] };

/** a place's total for the items, or null when any item has no price there */
export function placeTotal(lines: Line[]): { low: string; high: string } | null {
  if (!lines.length || lines.some((l) => l.low === null)) return null;
  const low = addDecimals(lines.map((l) => l.low as string));
  const high = addDecimals(lines.map((l) => (l.high ?? l.low) as string));
  return low && high ? { low, high } : null;
}

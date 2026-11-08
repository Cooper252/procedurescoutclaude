// Shared by the server pages (titles, structured data) and AreaView.
import { compareDecimal, money } from "./money";
import type { SearchResult } from "./types";

export function cashSummary(result: SearchResult | null): { min: string | null; n: number } {
  const heads = (result?.facilities ?? []).map((f) => f.headline).filter((h): h is string => !!h);
  heads.sort(compareDecimal);
  return { min: heads[0] ?? null, n: heads.length };
}

/** English answer used in the page description and FAQ structured data. */
export function costAnswer(result: SearchResult | null, place: string): string {
  const typ = result?.typical;
  const { min, n } = cashSummary(result);
  if (typ) {
    return `Published cash prices near ${place} range from ${money(typ.low)} to ${money(typ.high)} for the middle half of ${typ.count} places that published one. The lowest is ${money(min)}.`;
  }
  if (min) return `${n} places near ${place} published a cash price; the lowest is ${money(min)}.`;
  return `No place near ${place} has published a cash price for this yet.`;
}

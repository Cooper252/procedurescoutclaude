// Reading an insurance card photo on the person's own device (Cooper,
// 2026-11-12, option 1). The text is matched against the insurers we list; the
// photo and the text never leave the device. It suggests, the person chooses.

import type { Plan } from "./types";

export interface CardHint {
  payerId: string | null; // the insurer we think it is, if any
  payer: string | null;
  planType: string | null; // e.g. "HMO", "PPO", "Medicare", "Medicaid"
  found: string[]; // the words we recognized, shown to the person
}

const GENERIC = new Set([
  "health", "healthcare", "plan", "plans", "insurance", "company", "the", "and", "inc", "of",
  "care", "services", "network", "group", "member", "medical", "all", "one", "rate",
  "published", "for", "employee", "program",
]); // fmt: skip

// plan types as printed on cards, most specific first
const TYPES: [RegExp, string][] = [
  [/medicare\s+advantage|\bmapd?\b/i, "Medicare Advantage"],
  [/\bmedicare\b/i, "Medicare"],
  [/\bmedicaid\b|\bchip\b/i, "Medicaid"],
  [/marketplace|exchange|healthcare\.gov|health\s*link/i, "Marketplace"],
  [/\bfep\b|federal\s+employee/i, "Federal Employee Program"],
  [/\bepo\b/i, "EPO"],
  [/\bpos\b|point\s+of\s+service/i, "POS"],
  [/\bppo\b/i, "PPO"],
  [/\bhmo\b/i, "HMO"],
  [/\bhdhp\b|\bhsa\b/i, "HDHP"],
];

// common short names printed on cards
const ALSO: [RegExp, string][] = [
  [/\bbcbs\b|blue\s*cross|blue\s*shield/i, "blue cross"],
  [/\buhc\b|united\s*health/i, "unitedhealthcare"],
];

const words = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .split(/\s+/)
    .filter((w) => w.length >= 3 && !GENERIC.has(w));

export function matchCard(text: string, plans: Plan[]): CardHint {
  const textWords = new Set(words(text));
  for (const [re, add] of ALSO) if (re.test(text)) add.split(" ").forEach((w) => textWords.add(w));
  let best: { payerId: string; payer: string; score: number } | null = null;
  const seen = new Set<string>();
  for (const p of plans) {
    const key = p.payer_id || p.payer;
    if (seen.has(key)) continue;
    seen.add(key);
    const name = words(p.payer.replace(/\(.*?\)/g, ""));
    if (!name.length) continue;
    const hits = name.filter((w) => textWords.has(w)).length;
    const score = hits / name.length;
    if (hits > 0 && score >= 0.5 && (!best || score > best.score)) {
      best = { payerId: p.payer_id ?? "", payer: p.payer, score };
    }
  }
  const planType = TYPES.find(([re]) => re.test(text))?.[1] ?? null;
  const found = [best?.payer, planType].filter((x): x is string => !!x);
  return { payerId: best?.payerId || null, payer: best?.payer ?? null, planType, found };
}

// does a plan name fit the type read from the card?
export function fitsType(plan: Plan, type: string | null): boolean {
  if (!type) return false;
  const n = `${plan.plan} ${plan.segment} ${plan.product_type}`.toLowerCase();
  switch (type) {
    case "Medicare Advantage":
    case "Medicare":
      return n.includes("medicare");
    case "Medicaid":
      return n.includes("medicaid");
    case "Marketplace":
      return n.includes("marketplace") || n.includes("exchange");
    case "Federal Employee Program":
      return n.includes("federal");
    default:
      return n.includes(type.toLowerCase());
  }
}

export async function readCard(file: File): Promise<string> {
  const { createWorker } = await import("tesseract.js");
  const worker = await createWorker("eng", 1, {
    workerPath: "/ocr/worker.min.js",
    corePath: "/ocr",
    langPath: "/ocr/lang",
    gzip: true,
  });
  try {
    const { data } = await worker.recognize(file);
    return data.text;
  } finally {
    await worker.terminate();
  }
}

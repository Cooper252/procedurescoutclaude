"use client";

// Every published price for one place, explained (Cooper, 2026-11-12: "7
// different HMO prices ... and one of them just says 24.99%"). Prices are
// grouped by the part of the bill they cover as the hospital labeled them
// (its own part, the doctor's part), identical rows are shown once, and each
// row says its setting, what kind of rate it is and the hospital's own wording.

import type { Price } from "@/lib/types";
import { compareDecimal, formatMoney, money } from "@/lib/money";
import { useApp } from "./AppState";

const TYPE: Record<string, [string, string]> = {
  negotiated: ["Your plan's rate", "Tarifa de su plan"],
  discounted_cash: ["Cash price", "Precio en efectivo"],
  gross: ["Full price (almost nobody pays this)", "Precio completo (casi nadie lo paga)"],
  min: ["Lowest plan rate", "Tarifa más baja"],
  max: ["Highest plan rate", "Tarifa más alta"],
};
const TYPE_ORDER = ["negotiated", "discounted_cash", "gross", "min", "max"];

// common billing modifiers (CMS), in plain words
const MODIFIER: Record<string, [string, string]> = {
  "26": ["doctor's reading or service only", "solo la lectura o servicio del médico"],
  TC: ["equipment and staff only, no doctor's reading", "solo equipo y personal, sin la lectura del médico"],
  "50": ["both sides", "ambos lados"],
  LT: ["left side", "lado izquierdo"],
  RT: ["right side", "lado derecho"],
  "59": ["a separate service on the same day", "un servicio aparte el mismo día"],
  XU: ["a separate service on the same day", "un servicio aparte el mismo día"],
  "76": ["repeated by the same doctor", "repetido por el mismo médico"],
  "77": ["repeated by another doctor", "repetido por otro médico"],
  "52": ["reduced service", "servicio reducido"],
  "53": ["stopped before finishing", "suspendido antes de terminar"],
};

type Part = "facility" | "professional" | "unknown";

function partOf(p: Price): Part {
  if (p.billing_class === "professional") return "professional";
  if (p.billing_class === "facility" || p.billing_class === "both") return "facility";
  return "unknown";
}

export function PriceDetails({ prices }: { prices: Price[] }) {
  const { t, lang } = useApp();
  const es = lang === "es" ? 1 : 0;

  // identical rows once, with how many times the hospital listed them
  const seen = new Map<string, { p: Price; n: number }>();
  for (const p of prices) {
    const key = [p.price_type, p.payer, p.plan, p.amount, p.percentage, p.algorithm, p.setting, p.billing_class, (p.modifiers ?? []).join("|"), p.description, p.methodology, p.code].join("~");
    const got = seen.get(key);
    if (got) got.n += 1;
    else seen.set(key, { p, n: 1 });
  }
  const rows = Array.from(seen.values());
  const parts: Part[] = ["facility", "professional", "unknown"];
  const present = parts.filter((x) => rows.some((r) => partOf(r.p) === x));
  const partTitle: Record<Part, string> = {
    facility: t.partFacility,
    professional: t.partDoctor,
    unknown: present.length > 1 ? t.partUnknown : "",
  };

  function amountText(p: Price): string {
    if (formatMoney(p.amount)) return money(p.amount!);
    if (p.percentage) {
      return p.methodology === "percent_of_total_billed_charges"
        ? t.pctOfBill.replace("{p}", p.percentage)
        : t.pctOf.replace("{p}", p.percentage);
    }
    return p.algorithm ? t.byFormula : "—";
  }

  function notes(p: Price): string[] {
    const out: string[] = [];
    const setting = p.setting === "inpatient" ? t.setInpatient : p.setting === "outpatient" ? t.setOutpatient : null;
    if (setting) out.push(setting);
    if (p.methodology === "per_diem") out.push(t.methPerDiem);
    if (p.methodology === "case_rate") out.push(t.methCaseRate);
    for (const m of p.modifiers ?? []) {
      const known = MODIFIER[m.toUpperCase()];
      out.push(known ? known[es] : t.modifierCode.replace("{m}", m));
    }
    return out;
  }

  return (
    <div className="price-details">
      <details className="why-several">
        <summary>{t.whySeveralTitle}</summary>
        <p>{t.whySeveral}</p>
      </details>
      {present.map((part) => (
        <section key={part} className="pd-part">
          {partTitle[part] && <h5>{partTitle[part]}</h5>}
          {TYPE_ORDER.filter((ty) => rows.some((r) => partOf(r.p) === part && r.p.price_type === ty)).map((ty) => {
            const group = rows
              .filter((r) => partOf(r.p) === part && r.p.price_type === ty)
              .sort((a, b) => (a.p.amount && b.p.amount ? compareDecimal(a.p.amount, b.p.amount) : a.p.amount ? -1 : 1));
            return (
              <div key={ty} className="pd-group">
                <p className="pd-type">{(TYPE[ty] ?? [ty, ty])[es]}</p>
                <ul>
                  {group.map(({ p, n }, i) => (
                    <li key={i}>
                      <span className="pd-amount">{amountText(p)}</span>
                      <span className="pd-meta">
                        {p.plan && (
                          <span>
                            {p.payer} · {p.plan}
                            {p.plan_match === "all_plans" && <> ({t.pdAllPlans})</>}
                          </span>
                        )}
                        {notes(p).map((x) => (
                          <span key={x}>{x}</span>
                        ))}
                        {p.description && (
                          <span className="pd-wording">
                            {t.theirWording}: “{p.description}”
                          </span>
                        )}
                        <span className="code">{p.code}</span>
                        {n > 1 && <span>{t.listedTimes.replace("{n}", String(n))}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

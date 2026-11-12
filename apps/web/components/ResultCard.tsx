"use client";

import Link from "next/link";
import { useState } from "react";
import { fill, TYPE_ES, TYPE_EN } from "@/lib/i18n";
import { centsToDollars, estimate, type PlanDetails } from "@/lib/estimate";
import { compareDecimal, formatMoney, money, subtractDecimal, unitLabel } from "@/lib/money";
import type { Bundle, Facility, Mode } from "@/lib/types";
import { PriceDetails } from "./PriceDetails";
import { WholeCost } from "./WholeCost";
import { EmailMe } from "./EmailMe";
import { useApp } from "./AppState";
import { Alert, Chevron, Heart, Pin, TrendDown, TrendUp } from "./Icons";
import { Stars } from "./ProviderHome";
import { ReportPrice } from "./ReportPrice";

const PRICE_TYPE: Record<string, [string, string]> = {
  discounted_cash: ["Cash price", "Precio en efectivo"],
  gross: ["Full price", "Precio completo"],
  negotiated: ["Plan rate", "Tarifa del plan"],
  min: ["Lowest plan rate", "Tarifa más baja"],
  max: ["Highest plan rate", "Tarifa más alta"],
};

function date(iso: string | null, lang: "en" | "es"): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return d.toLocaleDateString(lang === "es" ? "es-US" : "en-US", { month: "short", year: "numeric" });
}

export function ResultCard({
  f,
  mode,
  unit,
  service,
  payer,
  plan,
  unsure = null,
  bundle = null,
  planId = null,
  insurerId = null,
  payerRaw = null,
  planLabel = null,
  codeSystem = null,
  code = null,
}: {
  f: Facility;
  mode: Mode;
  unit: string | null;
  service?: string;
  payer?: string;
  plan?: PlanDetails | null;
  unsure?: string | null; // insurer name: prices are a range across its plans
  bundle?: Bundle | null; // the whole procedure's parts, when we have them
  planId?: string | null;
  insurerId?: string | null;
  payerRaw?: string | null;
  planLabel?: string | null;
  codeSystem?: string | null;
  code?: string | null;
}) {
  const { t, lang } = useApp();
  // a rough "you'd pay" only from this plan's negotiated rate, never a list price
  const est =
    // only from one clear rate: with several published rates we can't tell which is yours
    mode === "plan" && !unsure && plan && f.headline && f.headline_price_type === "negotiated" &&
    !(f.headline_highest && compareDecimal(f.headline, f.headline_highest) !== 0)
      ? estimate(f.headline, plan)
      : null;
  const [open, setOpen] = useState(false);
  // "not sure which plan": lowest to highest rate across the insurer's plans
  // several published rates of the same kind: show lowest to highest, not just the lowest
  const ranged = !!(f.headline && f.headline_highest && compareDecimal(f.headline, f.headline_highest) !== 0);
  const head = ranged ? { text: `${money(f.headline!)}–${money(f.headline_highest!)}` } : formatMoney(f.headline);
  const provider = f.prices.some((p) => p.price_source === "provider_entered");
  const label =
    provider && mode === "cash"
      ? t.regularPrice
      : mode === "plan" && f.no_plan_rate
        ? t.cash
        : mode === "plan" && unsure
          ? fill(t.rangeTag, { payer: unsure })
        : mode === "plan"
      ? f.plan_rate_is_all_plans
        ? fill(t.allPlansTag, { payer: payer ?? "" })
        : t.plan
      : mode === "list"
        ? t.list
        : t.cash;
  const typeName = (c: string) =>
    (lang === "es" ? TYPE_ES[c] : undefined) ?? TYPE_EN[c] ?? c.replace(/_/g, " ").replace(/^\w/, (x) => x.toUpperCase());
  const change = f.change_percent_since_last_file;
  // the lowest published cash price, for "Cash price is lower: $X"
  const cashRows = f.prices.filter((p) => p.price_type === "discounted_cash" && p.amount);
  const cashMain = cashRows.filter((p) => p.billing_class !== "professional");
  const cashLow = (cashMain.length ? cashMain : cashRows)
    .map((p) => p.amount as string)
    .sort(compareDecimal)[0];
  const isHospital = f.provider_types.includes("hospital");
  const firstCode = f.prices[0]?.code;
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${f.name} ${f.city ?? ""} ${f.state}`)}`;

  return (
    <article className={f.lowest_near_you ? "result best" : "result"}>
      <div className="result-top">
        <div className="result-id">
          <h3>
            <Link className="result-name" href={`/facility/${f.facility_id}${service ? `?service=${service}` : ""}`}>
              {f.name}
            </Link>
          </h3>
          {f.rating_average && f.rating_count ? (
            <p className="result-rating">
              <Stars value={Number(f.rating_average)} size={14} /> {f.rating_average} ({f.rating_count})
            </p>
          ) : null}
          <p className="meta">
            <span>{f.provider_types.map(typeName).join(" · ")}</span>
            {f.delivery && f.delivery !== "in_person" && (
              <span className="badge">{f.delivery === "online" ? t.dlvOnline : t.dlvBoth}</span>
            )}
            <span aria-hidden="true">•</span>
            <span>
              <Pin size={14} /> {f.city ? `${f.city} · ` : ""}
              {f.distance_miles} mi
            </span>
          </p>
        </div>
        <div className="price">
          {head ? (
            <>
              <span className="price-label">{label}</span>
              <span className="price-num">{head.text}</span>
              <span className="price-unit">{unitLabel(unit, lang)}</span>
              {f.doctor_fee && (
                <span className="price-doctor">
                  {fill(t.doctorFeeLine, {
                    p:
                      f.doctor_fee_highest && compareDecimal(f.doctor_fee, f.doctor_fee_highest) !== 0
                        ? `${money(f.doctor_fee)}–${money(f.doctor_fee_highest)}`
                        : money(f.doctor_fee),
                  })}
                </span>
              )}
            </>
          ) : (
            <span className="price-none">
              {f.status !== "prices"
                ? t.noPrices
                : mode === "cash"
                  ? t.noCashPrice
                  : `${label}: —`}
            </span>
          )}
        </div>
      </div>

      {est && (
        <p className="estimate-line">
          <strong>{fill(t.estYouPay, { p: centsToDollars(est.cents) })}</strong>{" "}
          <span className="muted small">{t[`estHow_${est.how}` as const]}</span>
        </p>
      )}

      {f.special && (f.special.regular ?? f.headline) && (
        <div className="special">
          <span className="badge special-tag">{t.specialTag}</span>
          <div>
            <strong>
              {fill(f.special.who === "new_patients" ? t.specialNew : t.specialAll, { price: money(f.special.price) })}
            </strong>
            <span className="special-meta">
              {fill(t.specialSave, {
                save: money(subtractDecimal(f.special.regular ?? f.headline ?? "0", f.special.price)),
                regular: money(f.special.regular ?? f.headline ?? "0"),
              })}
              {f.special.ends_on && <> · {fill(t.specialEnds, { d: date(f.special.ends_on, lang) })}</>}
              {f.special.terms && <> · {f.special.terms}</>}
            </span>
          </div>
        </div>
      )}

      {mode === "plan" && f.no_plan_rate && <p className="no-plan-rate">{t.noPlanRate}</p>}
      {(f.lowest_near_you || f.below_typical || f.cash_cheaper_than_plan || f.headline_possible_error || change) && (
        <ul className="badges">
          {f.lowest_near_you && <li className="badge good">{t.badgeLowest}</li>}
          {f.below_typical && <li className="badge good-soft">{t.badgeBelow}</li>}
          {f.cash_cheaper_than_plan && (
            <li className="badge info">{fill(t.badgeCashCheaper, { price: cashLow ? money(cashLow) : "" }).replace(/:\s*$/, "")}</li>
          )}
          {f.headline_possible_error && (
            <li className="badge warn">
              <Alert size={13} /> {t.badgeCheck}
            </li>
          )}
          {change && (
            <li className={change.startsWith("-") ? "badge trend down" : "badge trend up"}>
              {change.startsWith("-") ? <TrendDown size={13} /> : <TrendUp size={13} />}
              {fill(change.startsWith("-") ? t.changeDown : t.changeUp, { p: change.replace("-", "") })}
            </li>
          )}
        </ul>
      )}

      {mode === "plan" && f.plan_rate_is_all_plans && (
        <p className="all-plans-note">
          <Alert size={15} /> {fill(t.allPlansNote, { payer: payer ?? "" })}
        </p>
      )}

      {f.status === "prices" ? (
        <p className="source">
          {provider
            ? fill(t.priceFromProvider, { d: date(f.prices_published_at, lang) })
            : fill(t.priceFromFile, { d: date(f.prices_published_at, lang) })}
          {!provider && <> · {t.facilityOnly}</>}
        </p>
      ) : (
        <p className="source">{t.noPricesHint}</p>
      )}

      {isHospital && (
        <Link href="/help-paying" className="free-hint">
          <Heart size={15} /> {t.freeHere}. <span>{t.freeHereLink}</span>
        </Link>
      )}

      <div className="result-actions">
        {f.prices.length > 0 && (
          <button type="button" className="btn ghost sm" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? t.hide : t.details} <Chevron size={16} className={open ? "flip" : ""} />
          </button>
        )}
        <a className="btn ghost sm" href={maps} target="_blank" rel="noopener noreferrer">
          <Pin size={16} /> {t.directions}
        </a>
        {f.status === "prices" && (
          <EmailMe
            facilityId={f.facility_id}
            service={service}
            codeSystem={codeSystem}
            code={code}
            mode={mode}
            planId={planId}
            payerId={insurerId}
            payer={payerRaw}
            planLabel={planLabel}
          />
        )}
      </div>

      {bundle && f.status === "prices" && (
        <WholeCost bundle={bundle} facilityId={f.facility_id} mode={mode} planId={planId} insurerId={insurerId} />
      )}

      {open && (
        <div className="details">
          <h4>{t.allPrices}</h4>
          <PriceDetails prices={f.prices} />
          {f.prices.some((p) => formatMoney(p.amount)?.rounded) && <p className="fine">* {t.roundedNote}</p>}
          {firstCode && <p className="tip">{fill(t.askTip, { c: firstCode })}</p>}
          <ReportPrice facilityId={f.facility_id} serviceKey={service ? `svc:${service}` : undefined} priceShown={f.headline} />
        </div>
      )}
    </article>
  );
}

"use client";

// Body of the service-by-place pages (/prices/...). The server page fetches
// the data and sets the title; this renders it in the person's language.

import Link from "next/link";
import { useApp } from "./AppState";
import { Heart } from "./Icons";
import { ResultCard } from "./ResultCard";
import { fill, SERVICE_ES } from "@/lib/i18n";
import { compareDecimal, money, unitLabel } from "@/lib/money";
import { cashSummary } from "@/lib/area";
import type { SearchResult } from "@/lib/types";

export interface AreaLink {
  href: string;
  label: string;
  slug?: string;
}

export function AreaView({
  place,
  serviceSlug,
  serviceName,
  result,
  radius,
  searchHref,
  otherServices,
  nearby,
}: {
  place: string;
  serviceSlug: string;
  serviceName: string;
  result: SearchResult | null;
  radius: string;
  searchHref: string;
  otherServices: AreaLink[];
  nearby: AreaLink[];
}) {
  const { t, lang } = useApp();
  const name = lang === "es" ? SERVICE_ES[serviceSlug] ?? serviceName : serviceName;
  const priced = (result?.facilities ?? []).filter((f) => f.status === "prices");
  const unpriced = (result?.facilities ?? []).filter((f) => f.status !== "prices");
  priced.sort((a, b) => (a.headline && b.headline ? compareDecimal(a.headline, b.headline) : a.headline ? -1 : 1));
  const { min, n } = cashSummary(result);
  const typ = result?.typical ?? null;
  const answer = typ
    ? fill(t.areaACostRange, { place, low: money(typ.low), high: money(typ.high), n: typ.count, min: money(min) })
    : min
      ? fill(t.areaACostFew, { place, n, min: money(min) })
      : fill(t.areaACostNone, { place });

  return (
    <div className="wrap page area">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/prices">{t.areaBrowse}</Link>
      </nav>
      <h1 className="page-title">{fill(t.areaTitle, { service: name, place })}</h1>
      <p className="lead">{fill(t.areaLead, { service: name, place })}</p>

      <div className="area-summary card">
        <div>
          <p className="eyebrow">{t.cash}</p>
          <p className="area-big">
            {typ ? `${money(typ.low)} – ${money(typ.high)}` : min ? `${t.from} ${money(min)}` : t.noPrices}
          </p>
          <p className="fine">
            {unitLabel(result?.unit, lang)} · {fill(t.areaWithin, { r: radius, place })}
          </p>
        </div>
        <Link className="btn primary" href={searchHref}>
          {t.areaSeeAll}
        </Link>
      </div>

      <div className="results-list area-list">
        {priced.map((f) => (
          <ResultCard key={f.facility_id} f={f} mode="cash" unit={result?.unit ?? null} service={serviceSlug} />
        ))}
      </div>
      {unpriced.length > 0 && (
        <>
          <h2 className="section-label">{t.noPricesSection}</h2>
          <div className="results-list muted">
            {unpriced.map((f) => (
              <ResultCard key={f.facility_id} f={f} mode="cash" unit={result?.unit ?? null} service={serviceSlug} />
            ))}
          </div>
        </>
      )}

      <aside className="disclaimer">
        <h2>{t.resultsDisclaimerTitle}</h2>
        <p>{t.resultsDisclaimer}</p>
      </aside>

      <Link href="/help-paying" className="care-inline">
        <Heart size={18} /> <strong>{t.bannerLead}</strong> {t.bannerNotLoan} {t.bannerCta} →
      </Link>

      <section className="faq">
        <h2>{t.areaFaqTitle}</h2>
        <details open>
          <summary>{fill(t.areaQCost, { service: name, place })}</summary>
          <p>{answer}</p>
        </details>
        <details>
          <summary>{fill(t.areaQFree, { service: name })}</summary>
          <p>
            {t.areaAFree} <Link href="/help-paying">{t.freeHereLink}</Link>
          </p>
        </details>
        <details>
          <summary>{t.areaQWhy}</summary>
          <p>{t.areaAWhy}</p>
        </details>
      </section>

      {otherServices.length > 0 && (
        <section className="area-links">
          <h2>{fill(t.areaOther, { place })}</h2>
          <ul className="chips">
            {otherServices.map((s) => (
              <li key={s.href}>
                <Link className="chip" href={s.href}>
                  {lang === "es" && s.slug ? (SERVICE_ES[s.slug] ?? s.label).replace(/ \(.*\)$/, "") : s.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      {nearby.length > 0 && (
        <section className="area-links">
          <h2>{t.areaNearby}</h2>
          <ul className="chips">
            {nearby.map((c) => (
              <li key={c.href}>
                <Link className="chip" href={c.href}>
                  {c.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

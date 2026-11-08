"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppState";
import { Heart } from "@/components/Icons";
import { ResultCard } from "@/components/ResultCard";
import { SearchForm } from "@/components/SearchForm";
import { api } from "@/lib/api";
import { fill, SERVICE_ES, TYPE_ES } from "@/lib/i18n";
import { compareDecimal, money, unitLabel } from "@/lib/money";
import type { Mode, Plan, ProviderType, SearchResult, Service } from "@/lib/types";

const RADII = ["5", "10", "25", "50", "100"];

export default function SearchPage() {
  return (
    <Suspense fallback={<div className="wrap page"><p className="loading">…</p></div>}>
      <Results />
    </Suspense>
  );
}

function Results() {
  const { t, lang, setPlace } = useApp();
  const router = useRouter();
  const sp = useSearchParams();
  const service = sp.get("service") ?? "";
  const zip = sp.get("zip");
  const latParam = sp.get("lat");
  const lngParam = sp.get("lng");
  // the full (chargemaster) price is not a choice here: almost nobody pays it (D-044);
  // it stays in each place's details and on the bill-help page
  const mode = (sp.get("mode") === "plan" ? "plan" : "cash") as Mode;
  const planId = sp.get("plan");
  const ptype = sp.get("type");
  const radius = RADII.includes(sp.get("r") ?? "") ? (sp.get("r") as string) : "25";
  const sort = sp.get("sort") === "near" ? "near" : "price";

  const [services, setServices] = useState<Service[]>([]);
  const [types, setTypes] = useState<ProviderType[]>([]);
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [coords, setCoords] = useState<{ lat: string; lng: string } | null>(
    latParam && lngParam ? { lat: latParam, lng: lngParam } : null,
  );
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    api.services().then(setServices).catch(() => setServices([]));
    api.providerTypes().then(setTypes).catch(() => setTypes([]));
  }, []);

  useEffect(() => {
    if (mode === "plan" && plans === null) api.plans().then(setPlans).catch(() => setPlans([]));
  }, [mode, plans]);

  useEffect(() => {
    if (latParam && lngParam) {
      setCoords({ lat: latParam, lng: lngParam });
      return;
    }
    if (!zip) {
      setCoords(null);
      return;
    }
    api
      .zip(zip)
      .then((p) => {
        setPlace(p);
        setCoords({ lat: p.lat, lng: p.lng });
      })
      .catch(() => setError(t.zipNotFound));
  }, [zip, latParam, lngParam]);

  useEffect(() => {
    if (!coords || !service) return;
    if (mode === "plan" && !planId) {
      setResult(null);
      return;
    }
    let live = true;
    setLoading(true);
    setError(null);
    api
      .search({ lat: coords.lat, lng: coords.lng, service, mode, planId, providerType: ptype, radius })
      .then((r) => live && setResult(r))
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [coords, service, mode, planId, ptype, radius, attempt]);

  const svc = services.find((s) => s.slug === service) ?? null;
  const name = svc ? (lang === "es" ? SERVICE_ES[svc.slug] ?? svc.name : svc.name) : result?.service_name ?? "";
  const unit = result?.unit ?? svc?.unit ?? null;

  function setParam(changes: Record<string, string | null>) {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(changes)) (v === null ? next.delete(k) : next.set(k, v));
    router.replace(`/search?${next.toString()}`, { scroll: false });
  }

  const priced = useMemo(() => {
    const rows = result?.facilities.filter((f) => f.status === "prices") ?? [];
    const byDistance = (a: { distance_miles: string }, b: { distance_miles: string }) =>
      compareDecimal(a.distance_miles, b.distance_miles);
    if (sort === "near") return [...rows].sort(byDistance);
    // lowest headline first; places without a headline of this kind go last, nearest first
    return [...rows].sort((a, b) =>
      a.headline && b.headline ? compareDecimal(a.headline, b.headline) || byDistance(a, b) : a.headline ? -1 : b.headline ? 1 : byDistance(a, b),
    );
  }, [result, sort]);
  const unpriced = useMemo(() => result?.facilities.filter((f) => f.status !== "prices") ?? [], [result]);
  const where = zip ?? (coords ? t.useLocation.toLowerCase() : "");

  if (!coords || editing || !service) {
    return (
      <div className="wrap page narrow">
        <h1 className="page-title">{name || t.navSearch}</h1>
        <div className="card search-card">
          <SearchForm
            initialService={svc ? { slug: svc.slug, name: svc.name } : null}
            initialZip={zip ?? ""}
            initialType={ptype}
          />
        </div>
        {error && <p className="form-error">{error}</p>}
      </div>
    );
  }

  const modes: { m: Mode; label: string; hint: string }[] = [
    { m: "cash", label: t.modeCash, hint: t.modeCashHint },
    { m: "plan", label: t.modePlan, hint: t.modePlanHint },
  ];

  return (
    <div className="results-page">
      <div className="results-head">
        <div className="wrap">
          <p className="eyebrow">{t.resultsFor}</p>
          <div className="results-title">
            <h1>
              {name} <span className="unit">{unitLabel(unit, lang)}</span>
            </h1>
            <button type="button" className="btn ghost sm" onClick={() => setEditing(true)}>
              {t.change}
            </button>
          </div>
          <p className="results-where">
            {t.near} <strong>{where}</strong> · {radius} mi
          </p>

          <fieldset className="modes">
            <legend>{t.payingHow}</legend>
            <div className="segmented two" role="radiogroup">
              {modes.map((x) => (
                <button
                  key={x.m}
                  type="button"
                  role="radio"
                  aria-checked={mode === x.m}
                  className={mode === x.m ? "seg on" : "seg"}
                  onClick={() => setParam({ mode: x.m === "cash" ? null : x.m, plan: x.m === "plan" ? planId : null })}
                >
                  {x.label}
                </button>
              ))}
            </div>
            <p className="mode-hint">{modes.find((x) => x.m === mode)?.hint}</p>
          </fieldset>

          {mode === "plan" && plans !== null && (
            plans.length === 0 ? (
              <p className="notice">{t.noPlansYet}</p>
            ) : (
              <div className="field plan-pick">
                <label htmlFor="plan">{t.pickPlan}</label>
                <select id="plan" value={planId ?? ""} onChange={(e) => setParam({ plan: e.target.value || null })}>
                  <option value="">—</option>
                  {Array.from(new Set(plans.map((p) => p.payer))).map((payer) => (
                    <optgroup key={payer} label={payer}>
                      {plans
                        .filter((p) => p.payer === payer)
                        .map((p) => (
                          <option key={p.plan_id} value={p.plan_id}>
                            {p.payer} · {p.plan}
                          </option>
                        ))}
                    </optgroup>
                  ))}
                </select>
              </div>
            )
          )}
        </div>
      </div>

      <div className="wrap results-body">
        {mode === "plan" && !planId && plans !== null && plans.length > 0 && (
          <p className="notice">{t.choosePlanFirst}</p>
        )}
        {loading && <ResultsSkeleton />}
        {error && !loading && (
          <div className="notice error">
            <strong>{t.errorTitle}</strong>
            <p>{error}</p>
            <button className="btn ghost sm" type="button" onClick={() => setAttempt((a) => a + 1)}>
              {t.tryAgain}
            </button>
          </div>
        )}
        {result && !loading && (
          <>
            {result.typical && (
              <div className="typical">
                <span className="typical-label">{t.typicalLine}</span>
                <span className="typical-range">
                  {money(result.typical.low)} – {money(result.typical.high)}
                </span>
                <span className="typical-of">{fill(t.typicalOf, { n: result.typical.count })}</span>
              </div>
            )}
            <div className="filters">
              <div className="field">
                <label htmlFor="f-r">{t.filterDistance}</label>
                <select id="f-r" value={radius} onChange={(e) => setParam({ r: e.target.value === "25" ? null : e.target.value })}>
                  {RADII.map((r) => (
                    <option key={r} value={r}>
                      {fill(t.withinMiles, { r })}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="f-t">{t.typeLabel}</label>
                <select id="f-t" value={ptype ?? ""} onChange={(e) => setParam({ type: e.target.value || null })}>
                  <option value="">{t.typeAny}</option>
                  {types.map((ty) => (
                    <option key={ty.code} value={ty.code}>
                      {lang === "es" ? TYPE_ES[ty.code] ?? ty.name : ty.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label htmlFor="f-s">{t.sortLabel}</label>
                <select id="f-s" value={sort} onChange={(e) => setParam({ sort: e.target.value === "price" ? null : e.target.value })}>
                  <option value="price">{t.sortPrice}</option>
                  <option value="near">{t.sortNear}</option>
                </select>
              </div>
            </div>
            <p className="count">
              {fill(t.facilityCount, { n: result.facilities.length, r: radius })} · {sort === "near" ? t.sortNear : t.sortedBy}
            </p>
            {result.facilities.length === 0 && (
              <div className="notice">
                <p>{fill(t.nothingNear, { r: radius })}</p>
                {RADII.indexOf(radius) < RADII.length - 1 && (
                  <button
                    className="btn ghost sm"
                    type="button"
                    onClick={() => setParam({ r: RADII[RADII.indexOf(radius) + 1]! })}
                  >
                    {fill(t.widenTo, { r: RADII[RADII.indexOf(radius) + 1]! })}
                  </button>
                )}
              </div>
            )}
            <div className="results-list">
              {priced.map((f) => (
                <ResultCard
                  key={f.facility_id}
                  f={f}
                  mode={mode}
                  unit={unit}
                  service={service}
                  payer={plans?.find((p) => p.plan_id === planId)?.payer}
                />
              ))}
            </div>
            {unpriced.length > 0 && (
              <>
                <h2 className="section-label">{t.noPricesSection}</h2>
                <div className="results-list muted">
                  {unpriced.map((f) => (
                    <ResultCard key={f.facility_id} f={f} mode={mode} unit={unit} service={service} />
                  ))}
                </div>
              </>
            )}
            {result.codes.length > 0 && (
              <p className="fine codes">
                {t.codesLabel}: {result.codes.join(", ")}
              </p>
            )}
            <aside className="disclaimer" aria-label={t.resultsDisclaimerTitle}>
              <h2>{t.resultsDisclaimerTitle}</h2>
              <p>{t.resultsDisclaimer}</p>
              <Link href="/disclaimer">{t.readMore}</Link>
            </aside>
            <Link href="/help-paying" className="care-inline">
              <Heart size={18} /> <strong>{t.bannerLead}</strong> {t.bannerCta} →
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <div className="results-list" aria-busy="true" aria-label="Loading">
      {[0, 1, 2].map((i) => (
        <div key={i} className="result skeleton">
          <div className="sk sk-title" />
          <div className="sk sk-line" />
          <div className="sk sk-line short" />
        </div>
      ))}
    </div>
  );
}

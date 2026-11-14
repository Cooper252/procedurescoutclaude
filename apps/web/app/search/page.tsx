"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppState";
import { Chevron, Heart, Pin, Video } from "@/components/Icons";
import { InsurancePicker, type Insurance } from "@/components/InsurancePicker";
import { ResultCard } from "@/components/ResultCard";
import { portalText } from "@/lib/i18n_portal";
import { SearchForm } from "@/components/SearchForm";
import { parseTypes, TypePicker } from "@/components/TypePicker";
import { api } from "@/lib/api";
import { fill, SERVICE_ES } from "@/lib/i18n";
import { EMPTY_PLAN, type PlanDetails } from "@/lib/estimate";
import { compareDecimal, money, unitLabel } from "@/lib/money";
import type { Bundle, Mode, Plan, ProviderType, SearchResult, Service } from "@/lib/types";

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
  const codeSystem = sp.get("code_system");
  const code = sp.get("code");
  const zip = sp.get("zip");
  const latParam = sp.get("lat");
  const lngParam = sp.get("lng");
  // the full (chargemaster) price is not a choice here: almost nobody pays it (D-044);
  // it stays in each place's details and on the bill-help page
  const mode = (sp.get("mode") === "plan" ? "plan" : "cash") as Mode;
  const planId = sp.get("plan");
  const payerRaw = sp.get("payer");
  // "not sure which plan": an insurance company's id (Cooper, 2026-11-12)
  const insurerId = sp.get("insurer");
  const kinds = parseTypes(sp.get("type"));
  const ptype = kinds.length ? kinds.join(",") : null;
  const radius = RADII.includes(sp.get("r") ?? "") ? (sp.get("r") as string) : "25";
  const online = sp.get("online") === "1";
  const [myPlan, setMyPlan] = useState<PlanDetails>(EMPTY_PLAN);
  const [planLoaded, setPlanLoaded] = useState(false);
  // phones: in person/online, distance, type and sort fold into one button (Cooper, 2026-11-14)
  const [filtersOpen, setFiltersOpen] = useState(false);
  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem("ps-plan");
      if (saved) setMyPlan({ ...EMPTY_PLAN, ...(JSON.parse(saved) as Partial<PlanDetails>) });
    } catch {
      /* private window: start empty */
    }
    setPlanLoaded(true);
  }, []);
  useEffect(() => {
    if (!planLoaded) return;
    try {
      window.sessionStorage.setItem("ps-plan", JSON.stringify(myPlan));
    } catch {
      /* private window: keep it in memory only */
    }
  }, [myPlan, planLoaded]);
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
  // Cooper (2026-11-12): after "Change" -> "Search prices" nothing came up,
  // because the edit form stayed open. Close it whenever the search changes.
  const spKey = sp.toString();
  useEffect(() => {
    setEditing(false);
  }, [spKey]);

  const [bundles, setBundles] = useState<Bundle[]>([]);
  useEffect(() => {
    api.bundles().then(setBundles).catch(() => setBundles([]));
  }, []);
  useEffect(() => {
    api.services().then(setServices).catch(() => setServices([]));
    api.providerTypes().then(setTypes).catch(() => setTypes([]));
  }, []);

  useEffect(() => {
    if (mode === "plan" && plans === null) api.plans().then(setPlans).catch(() => setPlans([]));
  }, [mode, plans]);
  const chosen: Insurance | null =
    mode !== "plan"
      ? null
      : planId
        ? (() => {
            const p = plans?.find((x) => x.plan_id === planId);
            return { plan: planId, label: p ? `${p.payer} · ${p.plan}` : "" };
          })()
        : insurerId
          ? (() => {
              const p = plans?.find((x) => x.payer_id === insurerId);
              return { insurer: insurerId, label: p ? t.insUnsureLabel.replace("{payer}", p.payer) : "" };
            })()
          : payerRaw
            ? { payer: payerRaw, label: payerRaw }
            : null;

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
    if (!coords || (!service && !code)) return;
    if (mode === "plan" && !planId && !payerRaw && !insurerId) {
      setResult(null);
      return;
    }
    let live = true;
    setLoading(true);
    setError(null);
    api
      .search({ lat: coords.lat, lng: coords.lng, service, codeSystem, code, mode, planId, payerRaw, insurerId, providerType: ptype, radius, online })
      .then((r) => live && setResult(r))
      .catch((e: Error) => live && setError(e.message))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [coords, service, codeSystem, code, mode, planId, payerRaw, insurerId, ptype, radius, online, attempt]);

  const svc = services.find((s) => s.slug === service) ?? null;
  const name = code
    ? `${codeSystem ?? ""} ${code}`
    : svc
      ? (lang === "es" ? SERVICE_ES[svc.slug] ?? svc.name : svc.name)
      : result?.service_name ?? "";
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
  // the whole procedure's parts: a bundle whose main piece is this service's code
  const bundle = useMemo(
    () => bundles.find((b) => b.components[0] && result?.codes.includes(b.components[0].code)) ?? null,
    [bundles, result],
  );
  const unpriced = useMemo(() => result?.facilities.filter((f) => f.status !== "prices") ?? [], [result]);
  const where = zip ?? (coords ? t.useLocation.toLowerCase() : "");

  if (!coords || editing || (!service && !code)) {
    return (
      <div className="wrap page narrow">
        <h1 className="page-title">{name || t.navSearch}</h1>
        <div className="card search-card">
          <SearchForm
            initialService={svc ? { slug: svc.slug, name: svc.name } : null}
            initialZip={zip ?? ""}
            initialType={ptype}
            initialRadius={radius}
            initialInsurance={chosen}
            initialOnline={online}
            onSearch={() => setEditing(false)}
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
          {svc?.about && !code && <p className="service-about">{svc.about}</p>}
          {code && result?.code_description && (
            <p className="code-wording">
              {t.codeWording}: “{result.code_description}”
            </p>
          )}
          <p className="results-where">
            {online ? (
              t.onlineWhere
            ) : (
              <>
                {t.near} <strong>{where}</strong> · {radius} mi
              </>
            )}
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
                  onClick={() =>
                  setParam({
                    mode: x.m === "cash" ? null : x.m,
                    plan: x.m === "plan" ? planId : null,
                    payer: x.m === "plan" ? payerRaw : null,
                    insurer: x.m === "plan" ? insurerId : null,
                  })
                }
                >
                  {x.label}
                </button>
              ))}
            </div>
            <p className="mode-hint">{modes.find((x) => x.m === mode)?.hint}</p>
          </fieldset>


          {mode === "plan" && (
            <div className="field plan-pick">
              <label htmlFor="plan">{t.pickPlan}</label>
              <InsurancePicker
                id="plan"
                value={chosen}
                near={coords}
                onChange={(v) =>
                  v &&
                  setParam({
                    plan: "plan" in v ? v.plan : null,
                    insurer: "insurer" in v ? v.insurer : null,
                    payer: "payer" in v ? v.payer : null,
                  })
                }
              />
            </div>
          )}
        </div>
      </div>

      <div className="wrap results-body">
        {mode === "plan" && !planId && !payerRaw && !insurerId && <p className="notice">{t.choosePlanFirst}</p>}
        {mode === "plan" && result?.insurer_unsure && (
          <p className="notice unsure-note">{t.insurerUnsureNote.replace("{payer}", result.insurer_unsure)}</p>
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
            <button
              type="button"
              className="btn ghost sm filters-toggle show-sm"
              aria-expanded={filtersOpen}
              aria-controls="more-filters"
              onClick={() => setFiltersOpen(!filtersOpen)}
            >
              <span>{filtersOpen ? t.filtersHide : t.filtersBtn}</span>
              <span className="filters-summary">
                {online ? t.onlineShort : `${radius} mi`} · {kinds.length ? fill(t.typeSome, { n: kinds.length }) : t.typeAnyShort} ·{" "}
                {sort === "near" ? t.sortShortNear : t.sortShortPrice}
              </span>
              <Chevron size={16} className={filtersOpen ? "flip" : ""} />
            </button>
            <div id="more-filters" className={filtersOpen ? "more-filters open" : "more-filters"}>
            {/* in person or online, as visible as how you pay (Cooper, 2026-11-12); inside Filters on phones */}
            <fieldset className="modes visit-modes">
              <legend>{t.visitHow}</legend>
              <div className="segmented two" role="radiogroup">
                <button type="button" role="radio" aria-checked={!online} className={!online ? "seg on" : "seg"} onClick={() => setParam({ online: null })}>
                  <Pin size={16} /> {t.visitInPerson}
                </button>
                <button type="button" role="radio" aria-checked={online} className={online ? "seg on" : "seg"} onClick={() => setParam({ online: "1" })}>
                  <Video size={16} /> {t.visitOnline}
                </button>
              </div>
              {online && <p className="mode-hint">{t.visitOnlineHint}</p>}
            </fieldset>
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
                <TypePicker
                  id="f-t"
                  types={types}
                  value={kinds}
                  onChange={(next) => setParam({ type: next.length ? next.join(",") : null })}
                />
              </div>
              <div className="field">
                <label htmlFor="f-s">{t.sortLabel}</label>
                <select id="f-s" value={sort} onChange={(e) => setParam({ sort: e.target.value === "price" ? null : e.target.value })}>
                  <option value="price">{t.sortPrice}</option>
                  <option value="near">{t.sortNear}</option>
                </select>
              </div>
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
            {result.sponsored && result.sponsored.length > 0 && (
              <aside className="sponsored" aria-label={portalText(lang).sponsored}>
                <span className="badge sponsored-tag">{portalText(lang).sponsored}</span>
                <ul>
                  {result.sponsored.map((s) => (
                    <li key={s.facility_id}>
                      <Link href={`/facility/${s.facility_id}${service ? `?service=${service}` : ""}`}>{s.name}</Link>
                      {s.city && <span className="muted"> · {s.city}</span>}
                    </li>
                  ))}
                </ul>
                <p className="fine">{portalText(lang).sponsoredNote}</p>
              </aside>
            )}
            {mode === "plan" && <EstimatePanel value={myPlan} onChange={setMyPlan} />}
            <div className="results-list">
              {priced.map((f) => (
                <ResultCard
                  key={f.facility_id}
                  f={f}
                  mode={mode}
                  unit={unit}
                  service={service}
                  payer={plans?.find((p) => p.plan_id === planId)?.payer}
                  unsure={result?.insurer_unsure ?? null}
                  bundle={bundle}
                  planId={planId}
                  insurerId={insurerId}
                  payerRaw={payerRaw}
                  planLabel={chosen?.label ?? null}
                  codeSystem={codeSystem}
                  code={code}
                  plan={mode === "plan" ? myPlan : null}
                />
              ))}
            </div>
            {online && priced.length === 0 && <p className="notice">{t.onlineNone}</p>}
            {unpriced.length > 0 && (
              // places without prices stay out of the way (Cooper, 2026-11-11)
              <details className="unpriced" open={priced.length === 0}>
                <summary className="section-label">
                  {fill(t.noPricesFold, { n: String(unpriced.length) })}
                </summary>
                <div className="results-list muted">
                  {unpriced.map((f) => (
                    <ResultCard key={f.facility_id} f={f} mode={mode} unit={unit} service={service} />
                  ))}
                </div>
              </details>
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
              <Heart size={18} /> <strong>{t.bannerLead}</strong> {t.bannerNotLoan} {t.bannerCta} →
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

// "What will I pay?": the visitor's own plan numbers, kept in this tab only.
function EstimatePanel({ value, onChange }: { value: PlanDetails; onChange: (p: PlanDetails) => void }) {
  const { t } = useApp();
  const field = (k: keyof PlanDetails, label: string, hint: string) => (
    <div className="field">
      <label htmlFor={`est-${k}`}>{label}</label>
      <input
        id={`est-${k}`}
        inputMode="decimal"
        value={value[k]}
        placeholder={hint}
        onChange={(e) => onChange({ ...value, [k]: e.target.value })}
      />
    </div>
  );
  return (
    <details className="card estimate-panel">
      <summary>
        <strong>{t.estTitle}</strong> <span className="muted small">{t.estSub}</span>
      </summary>
      <div className="estimate-fields">
        {field("deductibleLeft", t.estDeductible, "1000")}
        {field("coinsurance", t.estCoinsurance, "20")}
        {field("oopLeft", t.estOop, "4000")}
        {field("copay", t.estCopay, "40")}
      </div>
      <p className="fine">{t.estFine}</p>
    </details>
  );
}

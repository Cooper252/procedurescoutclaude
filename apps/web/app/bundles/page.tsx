"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import { useApp } from "@/components/AppState";
import { Pin } from "@/components/Icons";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import type { Bundle, Estimate, FacilityDetail, NearbyFacility } from "@/lib/types";

export default function BundlesPage() {
  return (
    <Suspense fallback={<div className="wrap page"><p className="loading">…</p></div>}>
      <Builder />
    </Suspense>
  );
}

function Builder() {
  const { t, place, setPlace } = useApp();
  const sp = useSearchParams();
  const router = useRouter();
  const [bundles, setBundles] = useState<Bundle[] | null>(null);
  const slug = sp.get("b");
  const facilityId = sp.get("facility");
  const [facility, setFacility] = useState<FacilityDetail | null>(null);
  const payment = "cash" as const;
  const [chosen, setChosen] = useState<string[]>([]);
  const [est, setEst] = useState<Estimate | null>(null);
  const [zip, setZip] = useState(place?.zip ?? "");
  const [near, setNear] = useState<NearbyFacility[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.bundles().then(setBundles).catch(() => setBundles([]));
  }, []);

  const bundle = useMemo(() => bundles?.find((b) => b.slug === slug) ?? bundles?.[0] ?? null, [bundles, slug]);

  useEffect(() => {
    if (bundle) setChosen(bundle.components.filter((c) => c.requirement !== "required" && c.included_by_default).map((c) => c.component_id));
  }, [bundle]);

  useEffect(() => {
    if (facilityId) api.facility(facilityId).then(setFacility).catch(() => setFacility(null));
    else setFacility(null);
  }, [facilityId]);

  useEffect(() => {
    if (!bundle || !facility) return;
    api
      .estimate(bundle.slug, { facilityId: facility.facility_id, payment, includeOptional: chosen })
      .then(setEst)
      .catch((e: Error) => setError(e.message));
  }, [bundle, facility, payment, chosen]);

  useEffect(() => {
    if (place && !facilityId && near === null) api.nearby(place.lat, place.lng).then(setNear).catch(() => setNear([]));
  }, [place, facilityId, near]);

  function go(params: Record<string, string | null>) {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(params)) (v === null ? next.delete(k) : next.set(k, v));
    router.replace(`/bundles?${next.toString()}`, { scroll: false });
  }

  async function findNear(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{5}$/.test(zip)) return setError(t.badZip);
    setError(null);
    try {
      const p = await api.zip(zip);
      setPlace(p);
      setNear(await api.nearby(p.lat, p.lng));
    } catch {
      setError(t.zipNotFound);
    }
  }

  if (bundles !== null && bundles.length === 0) {
    return (
      <div className="wrap page narrow">
        <h1 className="page-title">{t.bunTitle}</h1>
        <p className="notice">{t.bunNone}</p>
      </div>
    );
  }

  const lineFor = (id: string) => est?.lines.find((l) => l.component_id === id);

  return (
    <div className="wrap page bundles">
      <h1 className="page-title">{t.bunTitle}</h1>
      <p className="lead">{t.bunSub}</p>

      {bundles && (
        <div className="segmented bundle-tabs" role="tablist">
          {bundles.map((b) => (
            <button
              key={b.slug}
              type="button"
              role="tab"
              aria-selected={bundle?.slug === b.slug}
              className={bundle?.slug === b.slug ? "seg on" : "seg"}
              onClick={() => go({ b: b.slug })}
            >
              {b.name.replace(/, everything included$/, "")}
            </button>
          ))}
        </div>
      )}

      {!facility ? (
        <section className="card bun-pick">
          <h2>{t.bunPickPlace}</h2>
          <form className="bun-zip" onSubmit={findNear} noValidate>
            <div className="field">
              <label htmlFor="bun-zip">{t.bunPickPlaceHint}</label>
              <input id="bun-zip" inputMode="numeric" maxLength={5} placeholder={t.wherePlaceholder} value={zip} onChange={(e) => setZip(e.target.value.replace(/\D/g, ""))} />
            </div>
            <button className="btn primary" type="submit">
              {t.searchBtn}
            </button>
          </form>
          {error && <p className="form-error">{error}</p>}
          {near && (
            <ul className="pick-list">
              {near.map((n) => (
                <li key={n.facility_id}>
                  <button type="button" onClick={() => go({ facility: n.facility_id })}>
                    <strong>{n.name}</strong>
                    <span>
                      <Pin size={14} /> {n.city} · {n.distance_miles} mi
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        bundle && (
          <div className="bun-grid">
            <section className="card bun-pieces">
              <div className="bun-place">
                <div>
                  <p className="eyebrow">{bundle.name}</p>
                  <h2>
                    <Link href={`/facility/${facility.facility_id}`}>{facility.name}</Link>
                  </h2>
                </div>
                <button type="button" className="btn ghost sm" onClick={() => go({ facility: null })}>
                  {t.bunChange}
                </button>
              </div>
              <p className="eyebrow">{t.bunPayCash}</p>
              <ul className="pieces">
                {bundle.components.map((c) => {
                  const required = c.requirement === "required";
                  const on = required || chosen.includes(c.component_id);
                  const ln = lineFor(c.component_id);
                  return (
                    <li key={c.component_id} className={on ? "piece on" : "piece"}>
                      <label className="piece-check">
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={required}
                          onChange={(e) =>
                            setChosen((xs) => (e.target.checked ? [...xs, c.component_id] : xs.filter((x) => x !== c.component_id)))
                          }
                        />
                        <span className="piece-text">
                          <strong>{c.label}</strong>
                          <span className="piece-meta">
                            {required ? t.bunRequired : t.bunOptional} · <span className="code">{c.code}</span>
                          </span>
                        </span>
                      </label>
                      <div className="piece-price">
                        {!on ? (
                          <span className="muted">—</span>
                        ) : ln?.status === "priced" ? (
                          <span className="piece-amt">{money(ln.amount)}</span>
                        ) : ln?.status === "several_prices" ? (
                          <span className="piece-amt">{money(ln.amount)}</span>
                        ) : ln ? (
                          <span className="piece-missing">?</span>
                        ) : (
                          <span className="muted">…</span>
                        )}
                      </div>
                      {on && ln && ln.status !== "priced" && (
                        <p className="piece-note">
                          {ln.status === "not_published" ? t.bunNotPublished : ln.status === "not_a_dollar_amount" ? `${t.bunNotDollar} ${ln.rate ?? ""}` : ln.status === "several_prices" ? t.bunSeveral : ""}
                        </p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
            <aside className={est?.complete ? "card bun-total complete" : "card bun-total"}>
              <p className="eyebrow">{t.bunTotal}</p>
              <p className="bun-sum">{est ? money(est.total_of_priced_pieces) : "…"}</p>
              {est && <p className={est.complete ? "bun-state ok" : "bun-state"}>{est.complete ? t.bunComplete : t.bunIncomplete}</p>}
              <p className="fine">{t.resultsDisclaimer}</p>
            </aside>
          </div>
        )
      )}
    </div>
  );
}

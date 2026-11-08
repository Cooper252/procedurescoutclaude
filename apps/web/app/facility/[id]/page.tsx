"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { FileCheck, Heart, Phone, Pin, Globe, Alert } from "@/components/Icons";
import { api } from "@/lib/api";
import { fill, SERVICE_ES, TYPE_ES } from "@/lib/i18n";
import { formatMoney, unitLabel } from "@/lib/money";
import type { Bundle, FacilityDetail, FacilityPrices, Price, Service } from "@/lib/types";

export default function FacilityPage() {
  return (
    <Suspense fallback={<div className="wrap page"><p className="loading">…</p></div>}>
      <Facility />
    </Suspense>
  );
}

function day(iso: string | null, lang: "en" | "es"): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso);
  return d.toLocaleDateString(lang === "es" ? "es-US" : "en-US", { month: "long", day: "numeric", year: "numeric" });
}

function Facility() {
  const { t, lang } = useApp();
  const { id } = useParams<{ id: string }>();
  const sp = useSearchParams();
  const router = useRouter();
  const service = sp.get("service") ?? "";
  const [f, setF] = useState<FacilityDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [help, setHelp] = useState<string | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [prices, setPrices] = useState<FacilityPrices | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.facility(id).then(setF).catch(() => setMissing(true));
    api.services().then(setServices).catch(() => setServices([]));
    api.bundles().then(setBundles).catch(() => setBundles([]));
  }, [id]);

  useEffect(() => {
    if (f) api.facilityAssistance(f.facility_id, f.state).then((m) => setHelp(m.message)).catch(() => setHelp(null));
  }, [f]);

  useEffect(() => {
    if (!service || !f) {
      setPrices(null);
      return;
    }
    setLoading(true);
    api
      .facilityPrices(f.facility_id, service)
      .then(setPrices)
      .catch(() => setPrices(null))
      .finally(() => setLoading(false));
  }, [service, f]);

  if (missing) {
    return (
      <div className="wrap page narrow">
        <p className="notice">{t.facNotFound}</p>
      </div>
    );
  }
  if (!f) return <div className="wrap page"><p className="loading">…</p></div>;

  const typeName = (c: string) => (lang === "es" ? TYPE_ES[c] : undefined) ?? c.replace(/_/g, " ").replace(/^\w/, (x) => x.toUpperCase());
  const svcName = (s: Service) => (lang === "es" ? SERVICE_ES[s.slug] ?? s.name : s.name);
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${f.name} ${f.address ?? ""} ${f.city ?? ""} ${f.state}`)}`;
  const isHospital = f.provider_types.includes("hospital");

  const groups: { title: string; rows: Price[] }[] = prices
    ? [
        { title: t.groupCash, rows: prices.prices.filter((p) => p.price_type === "discounted_cash") },
        { title: t.groupPlans, rows: prices.prices.filter((p) => ["negotiated", "min", "max"].includes(p.price_type)) },
        { title: t.groupList, rows: prices.prices.filter((p) => p.price_type === "gross") },
      ].filter((g) => g.rows.length > 0)
    : [];

  return (
    <div className="wrap page facility">
      <button type="button" className="link-btn" onClick={() => router.back()}>
        ← {t.facBack}
      </button>

      <header className="fac-head card">
        <div>
          <p className="eyebrow">{f.provider_types.map(typeName).join(" · ")}</p>
          <h1 className="page-title">{f.name}</h1>
          <p className="fac-addr">
            <Pin size={16} /> {[f.address, f.city, `${f.state} ${f.zip ?? ""}`.trim()].filter(Boolean).join(", ")}
          </p>
          <ul className="fac-facts">
            {f.emergency_services && (
              <li>
                <Alert size={15} /> {t.facEr}
              </li>
            )}
            {f.cms_rating !== null && f.cms_rating_as_of && (
              <li>
                {t.facRating}: <strong>{"★".repeat(f.cms_rating)}{"☆".repeat(5 - f.cms_rating)}</strong>{" "}
                <span className="sr">{fill(t.facRatingOf, { n: f.cms_rating, d: day(f.cms_rating_as_of, lang) })}</span>
              </li>
            )}
          </ul>
        </div>
        <div className="fac-actions">
          {f.phone && (
            <a className="btn primary sm" href={`tel:${f.phone.replace(/[^\d+]/g, "")}`}>
              <Phone size={16} /> {t.facCall}
            </a>
          )}
          <a className="btn ghost sm" href={maps} target="_blank" rel="noopener noreferrer">
            <Pin size={16} /> {t.directions}
          </a>
          {f.website && (
            <a className="btn ghost sm" href={f.website} target="_blank" rel="noopener noreferrer">
              <Globe size={16} /> {t.facWebsite}
            </a>
          )}
        </div>
      </header>

      {(isHospital || help) && (
        <section className="fac-help">
          <h2>
            <Heart size={20} /> {t.facHelpTitle}
          </h2>
          <p>{help ?? "…"}</p>
          <Link className="btn care sm" href="/help-paying">
            {t.freeHereLink}
          </Link>
        </section>
      )}

      <section className="fac-prices card">
        <h2>{t.facPricesTitle}</h2>
        <div className="field">
          <label htmlFor="fac-svc">{t.facPickService}</label>
          <select
            id="fac-svc"
            value={service}
            onChange={(e) => router.replace(`/facility/${f.facility_id}${e.target.value ? `?service=${e.target.value}` : ""}`, { scroll: false })}
          >
            <option value="">—</option>
            {services.map((s) => (
              <option key={s.slug} value={s.slug}>
                {svcName(s)}
              </option>
            ))}
          </select>
        </div>
        {!f.prices_published_at && <p className="notice">{t.facNoFile}</p>}
        {loading && <p className="loading">{t.loading}</p>}
        {prices && !loading && prices.prices.length === 0 && f.prices_published_at && <p className="notice">{t.facNoPrices}</p>}
        {!loading &&
          groups.map((g) => (
            <div key={g.title} className="price-group">
              <h3>
                {g.title} <span className="unit">{unitLabel(prices?.unit, lang)}</span>
              </h3>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {g.rows.map((p, i) => {
                      const m = formatMoney(p.amount);
                      return (
                        <tr key={i}>
                          <td>{p.plan ? `${p.payer ?? ""} · ${p.plan}` : p.setting ?? "—"}</td>
                          <td className="num">
                            {m ? m.text : p.percentage ? `${p.percentage}%` : p.algorithm ?? "—"}
                            {m?.rounded && <span title={t.roundedNote}>*</span>}
                          </td>
                          <td className="code">{p.code}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        {prices && prices.prices.some((p) => formatMoney(p.amount)?.rounded) && <p className="fine">* {t.roundedNote}</p>}
        {prices && prices.codes[0] && <p className="tip">{fill(t.askTip, { c: prices.codes[0] })}</p>}
      </section>

      {bundles.length > 0 && (
        <section className="fac-bundles">
          <h2>{t.facWhole}</h2>
          <ul className="chips">
            {bundles.map((b) => (
              <li key={b.slug}>
                <Link className="chip" href={`/bundles?b=${b.slug}&facility=${f.facility_id}`}>
                  {b.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {f.prices_published_at && (
        <section className="fac-how">
          <h2>
            <FileCheck size={20} /> {t.facHowTitle}
          </h2>
          <p>{fill(t.facHow, { d: day(f.prices_published_at, lang) })}</p>
          <p className="fine">{t.resultsDisclaimer}</p>
        </section>
      )}

      <p className="fac-claim">
        <Link href="/providers">{t.facClaim}</Link>
      </p>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useApp } from "@/components/AppState";
import { CareFields } from "@/components/FreeCare";
import { Heart, Lock, Phone } from "@/components/Icons";
import { api } from "@/lib/api";
import { cleanIncome } from "@/lib/money";
import type { AssistanceCheck, AssistanceMessage, HealthCenter } from "@/lib/types";

export default function HelpPaying() {
  const { t, care, setCare, place, setPlace } = useApp();
  const id = useId();
  const [size, setSize] = useState(care?.householdSize ?? 1);
  const [income, setIncome] = useState(care?.income ?? "");
  const [zip, setZip] = useState(place?.zip ?? "");
  const [msg, setMsg] = useState<AssistanceMessage | null>(null);
  const [result, setResult] = useState<AssistanceCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [centers, setCenters] = useState<HealthCenter[] | null>(null);

  useEffect(() => {
    api.message(place?.state ?? null).then(setMsg).catch(() => setMsg(null));
  }, [place?.state]);

  async function run(sz: number, inc: string, z: string) {
    setError(null);
    const clean = cleanIncome(inc);
    if (!clean) return setError(t.careBadIncome);
    if (!/^\d{5}$/.test(z)) return setError(t.badZip);
    setBusy(true);
    try {
      const p = place?.zip === z ? place : await api.zip(z);
      setPlace(p);
      setCare({ householdSize: sz, income: clean });
      api.healthCenters(p.lat, p.lng).then(setCenters).catch(() => setCenters(null));
      const near = await api.nearby(p.lat, p.lng);
      if (near.length === 0) {
        setResult(null);
        setError(t.nothingNear.replace("{r}", "25"));
        return;
      }
      setResult(
        await api.check({ facilityIds: near.map((f) => f.facility_id), householdSize: sz, income: clean, state: p.state }),
      );
    } catch (e) {
      setError(e instanceof Error && e.message.includes("ZIP") ? t.zipNotFound : t.errorTitle);
    } finally {
      setBusy(false);
    }
  }

  // arriving from the home panel with answers and a known place: check right away
  useEffect(() => {
    if (care && place) void run(care.householdSize, care.income, place.zip);
  }, []);

  function submit(e: FormEvent) {
    e.preventDefault();
    void run(size, income, zip);
  }

  const order: Record<string, number> = {
    may_qualify_free: 0,
    may_qualify_discount: 1,
    policy_not_reviewed: 2,
    above_published_limits: 3,
  };
  const label: Record<string, string> = {
    may_qualify_free: t.helpResultFree,
    may_qualify_discount: t.helpResultDiscount,
    above_published_limits: t.helpResultAbove,
    policy_not_reviewed: t.helpResultUnknown,
  };

  return (
    <div className="wrap page help">
      <div className="help-grid">
        <div>
          <p className="eyebrow care-eyebrow">
            <Heart size={16} /> {t.navHelp}
          </p>
          <h1 className="page-title">{t.helpTitle}</h1>
          <p className="lead">{t.helpSub}</p>
          {msg && <p className="care-msg big">{msg.message}</p>}
        </div>
        <form className="card help-form" onSubmit={submit} noValidate>
          <CareFields size={size} setSize={setSize} income={income} setIncome={setIncome} />
          <div className="field">
            <label htmlFor={`${id}-zip`}>{t.helpZip}</label>
            <input
              id={`${id}-zip`}
              inputMode="numeric"
              autoComplete="postal-code"
              maxLength={5}
              placeholder={t.wherePlaceholder}
              value={zip}
              onChange={(e) => setZip(e.target.value.replace(/\D/g, ""))}
            />
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="btn care" type="submit" disabled={busy}>
            {busy ? "…" : t.helpCheck}
          </button>
          <p className="fine">
            <Lock size={14} /> {t.carePrivate}
          </p>
        </form>
      </div>

      {result && (
        <section className="help-results" aria-live="polite">
          <ul className="help-list">
            {[...result.facilities]
              .sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9))
              .map((f) => (
                <li key={f.facility_id} className={`help-item ${f.status}`}>
                  <div className="help-item-top">
                    <h3>{f.name}</h3>
                    <span className={`status ${f.status}`}>{label[f.status] ?? t.helpResultUnknown}</span>
                  </div>
                  <p>{f.message}</p>
                  <div className="result-actions">
                    {f.application_url && (
                      <a className="btn care sm" href={f.application_url} target="_blank" rel="noopener noreferrer">
                        {t.helpApply}
                      </a>
                    )}
                    {f.policy_url && (
                      <a className="btn ghost sm" href={f.policy_url} target="_blank" rel="noopener noreferrer">
                        {t.helpPolicy}
                      </a>
                    )}
                    {f.phone && (
                      <a className="btn ghost sm" href={`tel:${f.phone.replace(/[^\d+]/g, "")}`}>
                        <Phone size={15} /> {t.helpCall}
                      </a>
                    )}
                  </div>
                </li>
              ))}
          </ul>
          <p className="notice">
            {result.reminder} {t.helpDisclaimer} <Link href="/disclaimer">{t.readMore}</Link>
          </p>
        </section>
      )}

      {result && result.coverage && result.coverage.length > 0 && (
        <section className="coverage">
          <h2>{t.covTitle}</h2>
          <ul className="help-list">
            {result.coverage.map((c) => (
              <li key={`${c.program}-${c.group}`} className="help-item may_qualify_discount">
                <div className="help-item-top">
                  <h3>{c.label}</h3>
                </div>
                <p>{c.limit}</p>
                <div className="result-actions">
                  <a className="btn care sm" href={c.apply_url} target="_blank" rel="noopener noreferrer">
                    {t.covApply}
                  </a>
                </div>
              </li>
            ))}
          </ul>
          <p className="fine">{t.covNote}</p>
        </section>
      )}

      {centers !== null && (
        <section className="coverage">
          <h2>{t.chcTitle}</h2>
          <p className="lead small">{t.chcSub}</p>
          {centers.length === 0 ? (
            <p className="notice">{t.chcNone}</p>
          ) : (
            <ul className="help-list">
              {centers.map((h) => (
                <li key={`${h.name}-${h.address}`} className="help-item">
                  <div className="help-item-top">
                    <h3>{h.name}</h3>
                    <span className="status">{h.distance_miles} mi</span>
                  </div>
                  <p>{[h.address, h.city, h.zip].filter(Boolean).join(", ")}</p>
                  <div className="result-actions">
                    {h.phone && (
                      <a className="btn ghost sm" href={`tel:${h.phone.replace(/[^\d+]/g, "")}`}>
                        <Phone size={15} /> {t.helpCall}
                      </a>
                    )}
                    <a
                      className="btn ghost sm"
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${h.name} ${h.address ?? ""} ${h.city ?? ""}`)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t.directions}
                    </a>
                    {h.website && (
                      <a className="btn ghost sm" href={h.website} target="_blank" rel="noopener noreferrer">
                        {t.facWebsite}
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {place && (
        <section className="coverage">
          <h2>{t.freeClinicsTitle}</h2>
          <p className="lead small">{t.freeClinicsSub}</p>
          <a
            className="btn ghost"
            href={place.state === "NV" ? "https://www.nevada211.org/healthcare-services/community-clinics/" : "https://www.211.org/"}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t.freeClinicsLink}
          </a>
        </section>
      )}

      {place?.state === "NV" && (
        <section className="coverage">
          <h2>{t.nvLawTitle}</h2>
          <p>{t.nvLawBody}</p>
          <p className="small muted">{t.nvLawFine}</p>
          <a
            className="btn ghost"
            href="https://www.leg.state.nv.us/NRS/NRS-439B.html#NRS439BSec260"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t.nvLawLink}
          </a>
        </section>
      )}

      <section className="more-help">
        <h2>{t.helpNextTitle}</h2>
        <ul className="tiles">
          <li>{t.helpMedicaid}</li>
          <li>{t.helpChc}</li>
          <li>{t.helpAfter}</li>
          <li>{t.helpChecklist}</li>
        </ul>
      </section>
    </div>
  );
}

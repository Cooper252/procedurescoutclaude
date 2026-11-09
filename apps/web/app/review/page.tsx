"use client";

// Write a review from a one-time link (#token in the address, so it never
// reaches server logs). The link came by email from us or from the provider.

import Link from "next/link";
import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { fill } from "@/lib/i18n";
import { portalText } from "@/lib/i18n_portal";
import { portal } from "@/lib/portal";

export default function ReviewPage() {
  const { lang } = useApp();
  const p = portalText(lang);
  const [token, setToken] = useState<string | null>(null);
  const [info, setInfo] = useState<{ facility_id: string; facility_name: string } | null>(null);
  const [bad, setBad] = useState(false);
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [matched, setMatched] = useState<"yes" | "no" | "unsure" | "">("");
  const [name, setName] = useState("");
  const [visited, setVisited] = useState(false);
  const [independent, setIndependent] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = window.location.hash.slice(1);
    if (!t) {
      setBad(true);
      return;
    }
    setToken(t);
    portal.checkReviewLink(t).then(setInfo).catch(() => setBad(true));
  }, []);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !rating || body.trim().length < 20 || !name.trim() || !visited || !independent) {
      setErr(p.rNeed);
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await portal.submitReview({
        token,
        rating,
        title: title.trim() || null,
        body,
        price_matched: matched === "yes" ? true : matched === "no" ? false : null,
        display_name: name,
        visited,
        independent,
      });
      setDone(true);
      history.replaceState(null, "", window.location.pathname);
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (bad) {
    return (
      <div className="wrap page narrow">
        <p className="notice">{p.rExpired}</p>
      </div>
    );
  }
  if (!info) return <div className="wrap page narrow"><p className="loading">…</p></div>;
  if (done) {
    return (
      <div className="wrap page narrow">
        <div className="card review-card">
          <h1 className="page-title">{fill(p.rTitle, { name: info.facility_name })}</h1>
          <p className="notice good">{p.rThanks}</p>
          <Link className="btn ghost sm" href={`/facility/${info.facility_id}`}>
            ← {info.facility_name}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="wrap page narrow">
      <form className="card review-card" onSubmit={send} noValidate>
        <h1 className="page-title">{fill(p.rTitle, { name: info.facility_name })}</h1>
        <fieldset className="field">
          <legend>{p.rStars}</legend>
          <div className="star-pick" role="radiogroup">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                role="radio"
                aria-checked={rating === n}
                aria-label={fill(p.rStar, { n })}
                className={n <= rating ? "on" : undefined}
                onClick={() => setRating(n)}
              >
                ★
              </button>
            ))}
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor="rv-title">{p.rHeadline}</label>
          <input id="rv-title" maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="rv-body">{p.rBody}</label>
          <textarea id="rv-body" rows={6} maxLength={3000} value={body} onChange={(e) => setBody(e.target.value)} aria-describedby="rv-hint" />
          <p className="fine" id="rv-hint">
            {p.rBodyHint} ({body.trim().length}/3000)
          </p>
        </div>
        <fieldset className="field">
          <legend>{p.rMatched}</legend>
          <div className="segmented">
            {(
              [
                ["yes", p.yes],
                ["no", p.no],
                ["unsure", p.notSure],
              ] as const
            ).map(([v, label]) => (
              <label key={v} className={matched === v ? "seg on" : "seg"}>
                <input type="radio" name="matched" value={v} checked={matched === v} onChange={() => setMatched(v)} /> {label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor="rv-name">{p.rName}</label>
          <input id="rv-name" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" />
        </div>
        <label className="check">
          <input type="checkbox" checked={visited} onChange={(e) => setVisited(e.target.checked)} /> {p.rVisited}
        </label>
        <label className="check">
          <input type="checkbox" checked={independent} onChange={(e) => setIndependent(e.target.checked)} /> {p.rIndependent}
        </label>
        {err && <p className="form-error">{err}</p>}
        <button className="btn primary" disabled={busy}>
          {p.rSubmit}
        </button>
        <p className="fine">{p.rules}</p>
      </form>
    </div>
  );
}

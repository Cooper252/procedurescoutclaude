"use client";

// The provider-written part of a facility page (D-050): logo, about, hours,
// languages, access, insurance note, photos and patient reviews. Everything
// here was checked by a person before it shows.

import { useState } from "react";
import { useApp } from "@/components/AppState";
import { Globe, Shield } from "@/components/Icons";
import { fill } from "@/lib/i18n";
import { portalText } from "@/lib/i18n_portal";
import { portal, track, type ProviderPage, type Review } from "@/lib/portal";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

export function Stars({ value, size = 16, label }: { value: number; size?: number; label?: string }) {
  const full = Math.round(value);
  return (
    <span className="stars" role="img" aria-label={label ?? `${value} / 5`} style={{ fontSize: size }}>
      {"★".repeat(full)}
      <span className="stars-off">{"★".repeat(5 - full)}</span>
    </span>
  );
}

function time(hhmm: string, lang: "en" | "es"): string {
  const [h, m] = hhmm.split(":").map(Number);
  const d = new Date(2000, 0, 1, h, m);
  return d.toLocaleTimeString(lang === "es" ? "es-US" : "en-US", { hour: "numeric", minute: m ? "2-digit" : undefined });
}

function day(iso: string, lang: "en" | "es"): string {
  return new Date(iso + "T12:00:00").toLocaleDateString(lang === "es" ? "es-US" : "en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function ProviderHome({ page }: { page: ProviderPage }) {
  const { lang } = useApp();
  const p = portalText(lang);
  const prof = page.profile;
  const today = DAYS[(new Date().getDay() + 6) % 7];

  return (
    <>
      {prof && (
        <section className="card ph-about">
          <div className="ph-about-head">
            {page.logo_url && <img className="ph-logo" src={page.logo_url} alt="" width={64} height={64} />}
            <div>
              <h2>{p.about}</h2>
              <p className="ph-claimed">
                <Shield size={15} /> {p.claimed}
              </p>
            </div>
          </div>
          {prof.about && <p className="ph-text">{prof.about}</p>}
          <div className="ph-grid">
            {Object.keys(prof.hours).length > 0 && (
              <div>
                <h3>{p.hours}</h3>
                <table className="ph-hours">
                  <tbody>
                    {DAYS.filter((d) => prof.hours[d]).map((d) => (
                      <tr key={d} className={d === today ? "today" : undefined}>
                        <th scope="row">{p.days[d]}</th>
                        <td>
                          {prof.hours[d] === "closed"
                            ? p.closed
                            : (prof.hours[d] ?? "")
                                .split("-")
                                .map((x) => time(x, lang))
                                .join(" – ")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div>
              {prof.languages.length > 0 && (
                <>
                  <h3>{p.languages}</h3>
                  <ul className="chips static">
                    {prof.languages.map((l) => (
                      <li key={l} className="chip">
                        {l}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {prof.accessibility.length > 0 && (
                <>
                  <h3>{p.access}</h3>
                  <ul className="ph-checks">
                    {prof.accessibility.map((a) => (
                      <li key={a}>✓ {p.accessLabels[a] ?? a}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          </div>
          {prof.insurance_note && (
            <div className="ph-ins">
              <h3>{p.insurance}</h3>
              <p>{prof.insurance_note}</p>
              <p className="fine">{p.insuranceFine}</p>
            </div>
          )}
          <div className="ph-links">
            {prof.booking_url && (
              <a
                className="btn primary sm"
                href={prof.booking_url}
                target="_blank"
                rel="noopener noreferrer nofollow ugc"
                onClick={() => track(page.facility_id, "booking_click")}
              >
                {p.book}
              </a>
            )}
            {prof.website_url && (
              <a
                className="btn ghost sm"
                href={prof.website_url}
                target="_blank"
                rel="noopener noreferrer nofollow ugc"
                onClick={() => track(page.facility_id, "website_click")}
              >
                <Globe size={16} /> {new URL(prof.website_url).hostname.replace(/^www\./, "")}
              </a>
            )}
          </div>
          <p className="fine">
            {p.fromProvider}
            {prof.updated_at && <> {fill(p.updated, { d: day(prof.updated_at, lang) })}</>}
          </p>
        </section>
      )}

      {page.photos.length > 0 && (
        <section className="ph-photos">
          <h2>{p.photos}</h2>
          <div className="ph-gallery">
            {page.photos.map((ph) => (
              <img key={ph.url} src={ph.url} alt={ph.alt ?? ""} loading="lazy" />
            ))}
          </div>
        </section>
      )}

    </>
  );
}

function ReviewItem({ r }: { r: Review }) {
  const { lang } = useApp();
  const p = portalText(lang);
  return (
    <li className="rv">
      <div className="rv-top">
        <Stars value={r.rating} label={fill(p.rStar, { n: r.rating })} />
        <span className="rv-name">{r.display_name}</span>
        <span className="rv-date">{day(r.published_at, lang)}</span>
      </div>
      {r.title && <h3 className="rv-title">{r.title}</h3>}
      <p className="rv-body">{r.body}</p>
      <p className="rv-meta">
        <span className="badge">{r.verification === "email" ? p.vEmail : p.vInvite}</span>
        {r.price_matched === true && <span className="badge good">{p.matchedYes}</span>}
        {r.price_matched === false && <span className="badge warn">{p.matchedNo}</span>}
      </p>
      {r.reply_body && (
        <div className="rv-reply">
          <strong>{p.reply}</strong>
          <p>{r.reply_body}</p>
        </div>
      )}
    </li>
  );
}

export function ProviderReviews({ page, facilityName }: { page: ProviderPage; facilityName: string }) {
  const { lang } = useApp();
  const p = portalText(lang);
  const s = page.reviews;
  const [list, setList] = useState<Review[]>(page.latest_reviews);
  const [more, setMore] = useState(page.reviews.count > page.latest_reviews.length);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [err, setErr] = useState("");
  const [dev, setDev] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("sending");
    try {
      const r = await portal.requestReview(page.facility_id, email);
      setDev(r.dev_link);
      setState("sent");
    } catch (ex) {
      setErr((ex as Error).message);
      setState("error");
    }
  };

  return (
    <section className="card ph-reviews" id="reviews">
      <h2>{p.reviews}</h2>
      {s.count > 0 && s.average ? (
        <div className="rv-summary">
          <div className="rv-avg">
            <strong>{s.average}</strong>
            <Stars value={Number(s.average)} size={20} />
            <span>{s.count === 1 ? p.basedOnOne : fill(p.basedOn, { n: s.count })}</span>
          </div>
          <div className="rv-bars" aria-hidden="true">
            {[5, 4, 3, 2, 1].map((n) => (
              <div key={n} className="rv-bar">
                <span>{n}★</span>
                <span className="rv-track">
                  <span style={{ width: `${(100 * (s.stars[n - 1] ?? 0)) / Math.max(1, s.count)}%` }} />
                </span>
                <span>{s.stars[n - 1] ?? 0}</span>
              </div>
            ))}
          </div>
          {s.price_matched_answered > 0 && (
            <p className="rv-matched">{fill(p.priceMatched, { y: s.price_matched_yes, n: s.price_matched_answered })}</p>
          )}
        </div>
      ) : (
        <p className="muted">{p.noReviews}</p>
      )}
      {s.removed > 0 && <p className="fine">{fill(p.removedNote, { n: s.removed })}</p>}

      {list.length > 0 && (
        <ul className="rv-list">
          {list.map((r) => (
            <ReviewItem key={r.id} r={r} />
          ))}
        </ul>
      )}
      {more && (
        <button
          type="button"
          className="btn ghost sm"
          onClick={() =>
            portal.moreReviews(page.facility_id, list.length).then((r) => {
              setList([...list, ...r]);
              if (r.length < 20) setMore(false);
            })
          }
        >
          {p.showMore}
        </button>
      )}

      <div className="rv-write">
        <h3>{p.write}</h3>
        {!page.reviews_enabled ? (
          <p className="muted">{p.reviewsOff}</p>
        ) : state === "sent" ? (
          <>
            <p className="notice good">{p.sent}</p>
            {dev && (
              <p className="fine">
                {p.devLink}: <a href={dev}>{dev}</a>
              </p>
            )}
          </>
        ) : (
          <form onSubmit={send} className="rv-form">
            <p className="muted">{fill(p.writeSub, { name: facilityName })}</p>
            <div className="field">
              <label htmlFor="rv-email">{p.email}</label>
              <input id="rv-email" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <button className="btn primary sm" disabled={state === "sending"}>
              {p.send}
            </button>
            {state === "error" && <p className="form-error">{err}</p>}
          </form>
        )}
        <button type="button" className="link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
          {p.rulesLink}
        </button>
        {open && <p className="fine">{p.rules}</p>}
      </div>
      {!page.claimed && <p className="ph-unclaimed fine">{p.notClaimed}</p>}
    </section>
  );
}

"use client";

// Provider account (D-050): second step, claiming a page, numbers, the
// homepage editor, images and reviews. Every change is reviewed by a person
// before it shows on the public page.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { AddPractice } from "@/components/AddPractice";
import { PortalPlan } from "@/components/PortalPlan";
import { PortalPrices } from "@/components/PortalPrices";
import { Stars } from "@/components/ProviderHome";
import { fill } from "@/lib/i18n";
import { portalText, type PortalDict } from "@/lib/i18n_portal";
import { portal, type Dashboard, type FacilityHit, type Me, type Num, type Profile, type ProfileEdit, type ProviderReview } from "@/lib/portal";

type Tab = "overview" | "prices" | "page" | "reviews" | "plan";

export default function Account() {
  const { lang } = useApp();
  const p = portalText(lang);
  const [me, setMe] = useState<Me | null>(null);
  const [state, setState] = useState<"loading" | "out" | "in">("loading");
  const [fid, setFid] = useState<string>("");
  const [tab, setTab] = useState<Tab>("overview");

  const load = useCallback(() => {
    portal
      .me()
      .then((m) => {
        setMe(m);
        setState("in");
        const active = m.memberships.find((x) => x.status === "active");
        setFid((cur) => cur || active?.facility_id || "");
      })
      .catch(() => setState("out"));
  }, []);
  useEffect(load, [load]);

  if (state === "loading") return <div className="wrap page"><p className="loading">…</p></div>;
  if (state === "out" || !me) {
    return (
      <div className="wrap page narrow">
        <p className="notice">{p.notSignedIn}</p>
        <Link className="btn primary" href="/providers/sign-in">
          {p.newLink}
        </Link>
      </div>
    );
  }

  const active = me.memberships.filter((m) => m.status === "active");
  const pending = me.memberships.filter((m) => m.status === "pending");
  const current = active.find((m) => m.facility_id === fid);

  return (
    <div className="wrap page acct">
      <div className="acct-head">
        <div>
          <p className="eyebrow">{p.account}</p>
          <h1 className="page-title">{current?.facility_name ?? me.email}</h1>
          <p className="muted">{me.email}</p>
        </div>
        <button
          type="button"
          className="btn ghost sm"
          onClick={() => portal.signOut().finally(() => (window.location.href = "/providers/sign-in"))}
        >
          {p.signOut}
        </button>
      </div>

      {!me.mfa_passed ? (
        <Mfa me={me} onDone={setMe} p={p} />
      ) : (
        <>
          {me.staff && (
            <div className="notice">
              <strong>{p.staffTitle}</strong>
              <ul>
                <li><a href="/admin/reviews">{p.staffFiles}</a></li>
                <li><a href="/admin/providers">{p.staffProviders}</a></li>
              </ul>
            </div>
          )}
          {active.length > 1 && (
            <div className="field acct-switch">
              <select value={fid} onChange={(e) => setFid(e.target.value)} aria-label="Facility">
                {active.map((m) => (
                  <option key={m.facility_id} value={m.facility_id}>
                    {m.facility_name}
                  </option>
                ))}
              </select>
            </div>
          )}
          {pending.map((m) => (
            <p key={m.facility_id} className="notice">
              {m.facility_name}: {p.pending}
            </p>
          ))}
          {current ? (
            <>
              <nav className="acct-tabs" role="tablist">
                {(
                  [
                    ["overview", p.tabOverview],
                    ["prices", p.tabPrices],
                    ["page", p.tabPage],
                    ["reviews", p.tabReviews],
                    ["plan", p.tabPlan],
                  ] as const
                ).map(([k, label]) => (
                  <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : undefined} onClick={() => setTab(k)}>
                    {label}
                  </button>
                ))}
              </nav>
              <p className="acct-public-row">
                <Link className="acct-public" href={`/facility/${current.facility_id}`}>
                  {p.viewPage} →
                </Link>
              </p>
              {tab === "overview" && <Overview fid={current.facility_id} p={p} />}
              {tab === "plan" && <PortalPlan fid={current.facility_id} isOwner={current.role === "owner"} />}
              {tab === "prices" && <PortalPrices fid={current.facility_id} canEdit={current.role !== "viewer"} />}
              {tab === "page" && <PageEditor fid={current.facility_id} p={p} canEdit={current.role !== "viewer"} />}
              {tab === "reviews" && <ReviewsTab fid={current.facility_id} p={p} canEdit={current.role !== "viewer"} />}
            </>
          ) : null}
          <Claim p={p} onClaimed={load} />
        </>
      )}
    </div>
  );
}

// ----------------------------------------------------------------- MFA
function Mfa({ me, onDone, p }: { me: Me; onDone: (m: Me) => void; p: PortalDict }) {
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  return (
    <section className="card acct-card">
      <h2>{p.mfaTitle}</h2>
      <p>{me.mfa_enabled ? p.mfaEnter : p.mfaWhy}</p>
      {!me.mfa_enabled && !setup && (
        <button className="btn primary" onClick={() => portal.mfaSetup().then(setSetup).catch((e) => setErr((e as Error).message))}>
          {p.mfaStart}
        </button>
      )}
      {setup && (
        <div className="mfa-key">
          <p>{p.mfaKey}</p>
          <code>{setup.secret.replace(/(.{4})/g, "$1 ").trim()}</code>
          <p>
            <a href={setup.otpauth_uri}>{p.mfaOpen}</a>
          </p>
        </div>
      )}
      {(me.mfa_enabled || setup) && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setErr("");
            portal.mfaVerify(code).then(onDone).catch((ex) => setErr((ex as Error).message));
          }}
        >
          <div className="field">
            <label htmlFor="mfa">{p.mfaCode}</label>
            <input id="mfa" inputMode="numeric" autoComplete="one-time-code" maxLength={7} value={code} onChange={(e) => setCode(e.target.value)} />
          </div>
          <button className="btn primary">{p.mfaVerify}</button>
        </form>
      )}
      {err && <p className="form-error">{err}</p>}
    </section>
  );
}

// --------------------------------------------------------------- claim
function Claim({ p, onClaimed }: { p: PortalDict; onClaimed: () => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<FacilityHit[]>([]);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    if (q.trim().length < 3) {
      setHits([]);
      return;
    }
    const h = setTimeout(() => portal.findFacility(q.trim()).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(h);
  }, [q]);
  return (
    <section className="card acct-card acct-claim">
      <h2>{p.claimTitle}</h2>
      <p className="muted">{p.claimSub}</p>
      <div className="field">
        <label htmlFor="claim-q">{p.claimSearch}</label>
        <input id="claim-q" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {hits.length > 0 && (
        <>
          <div className="field">
            <label htmlFor="claim-note">{p.claimNote}</label>
            <input id="claim-note" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          <ul className="claim-hits">
            {hits.map((h) => (
              <li key={h.facility_id}>
                <span>
                  <strong>{h.name}</strong> <span className="muted">{[h.city, h.state].filter(Boolean).join(", ")}</span>
                  {h.claimed && <span className="badge">{p.claimedAlready}</span>}
                </span>
                <button
                  className="btn ghost sm"
                  onClick={() =>
                    portal
                      .claim(h.facility_id, note.trim() || null)
                      .then(onClaimed)
                      .catch((e) => setErr((e as Error).message))
                  }
                >
                  {p.claimBtn}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {err && <p className="form-error">{err}</p>}
      <AddPractice />
    </section>
  );
}

// ------------------------------------------------------------ overview
function NumTile({ label, n, days, p }: { label: string; n: Num | undefined; days: number; p: PortalDict }) {
  const small = 10;
  const show = (v: number | null) => (v === null ? fill(p.fewer, { n: small }) : v.toLocaleString());
  return (
    <div className="tile">
      <span className="tile-label">{label}</span>
      <strong className={n?.value === null ? "tile-num small" : "tile-num"}>{show(n?.value ?? null)}</strong>
      <span className="tile-sub">{fill(p.vsBefore, { p: show(n?.previous ?? null), n: days })}</span>
    </div>
  );
}

function Overview({ fid, p }: { fid: string; p: PortalDict }) {
  const [days, setDays] = useState(30);
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setD(null);
    portal.stats(fid, days).then(setD).catch((e) => setErr((e as Error).message));
  }, [fid, days]);
  const v = (x: number | null) => (x === null ? fill(p.fewer, { n: 10 }) : x.toLocaleString());
  if (err) return <p className="form-error">{err}</p>;
  if (!d) return <p className="loading">…</p>;
  return (
    <div className="acct-overview">
      <div className="segmented acct-period" role="radiogroup" aria-label={p.period}>
        {[7, 30, 90].map((n) => (
          <button key={n} role="radio" aria-checked={days === n} className={days === n ? "seg on" : "seg"} onClick={() => setDays(n)}>
            {fill(p.lastDays, { n })}
          </button>
        ))}
      </div>
      <div className="tiles acct-tiles">
        <NumTile label={p.views} n={d.counts.page_view} days={days} p={p} />
        <NumTile label={p.shown} n={d.counts.search_impression} days={days} p={p} />
        <NumTile label={p.clicksWeb} n={d.counts.website_click} days={days} p={p} />
        <NumTile label={p.clicksPhone} n={d.counts.phone_click} days={days} p={p} />
        <NumTile label={p.clicksDir} n={d.counts.directions_click} days={days} p={p} />
        <NumTile label={p.clicksBook} n={d.counts.booking_click} days={days} p={p} />
        <div className="tile">
          <span className="tile-label">{p.avgPos}</span>
          <strong className="tile-num">{d.average_position ?? "—"}</strong>
        </div>
      </div>
      <p className="fine">{p.privacyNote}</p>

      <section className="card acct-card">
        <h2>{p.demandTitle}</h2>
        <p className="muted">{p.demandSub}</p>
        {!d.has_location && <p className="notice">{p.noLocation}</p>}
        {d.services.length > 0 && (
          <div className="table-wrap">
            <table className="acct-table">
              <thead>
                <tr>
                  <th>{p.svc}</th>
                  <th className="num">{fill(p.within, { n: 10 })}</th>
                  <th className="num">{fill(p.within, { n: 25 })}</th>
                  <th className="num">{fill(p.within, { n: 50 })}</th>
                  <th className="num">{p.youShown}</th>
                </tr>
              </thead>
              <tbody>
                {d.services.map((s) => (
                  <tr key={s.service_key}>
                    <td>{s.name}</td>
                    <td className="num">{v(s.searches_10)}</td>
                    <td className="num">{v(s.searches_25)}</td>
                    <td className="num">{v(s.searches_50)}</td>
                    <td className="num">{v(s.shown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <h3>{p.missedTitle}</h3>
        {d.missed.length === 0 ? (
          <p className="muted">{p.missedNone}</p>
        ) : (
          <ul className="acct-missed">
            {d.missed.map((s) => (
              <li key={s.service_key}>
                <strong>{s.name}</strong> <span className="muted">· {fill(p.within, { n: 25 })}: {v(s.searches_25)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card acct-card acct-boost">
        <h2>{p.boostTitle}</h2>
        <p className="muted">{fill(p.boostSub, { s: d.sponsors_per_page })}</p>
        <p className="notice">{p.boostNotYet}</p>
        {d.days !== 30 ? (
          <p className="muted">{p.boost30}</p>
        ) : (
          <div className="table-wrap">
            <table className="acct-table">
              <thead>
                <tr>
                  <th>{p.svc}</th>
                  <th className="num">{p.distance}</th>
                  <th className="num">{p.boostSearches}</th>
                  <th className="num">{p.boostViews}</th>
                  <th className="num">{p.boostNow}</th>
                </tr>
              </thead>
              <tbody>
                {d.boosts.map((b) => (
                  <tr key={b.service_key + b.ring_miles}>
                    <td>{b.name}</td>
                    <td className="num">{b.ring_miles} mi</td>
                    <td className="num">{v(b.searches)}</td>
                    <td className="num">
                      <strong>{b.estimated_views === null ? v(null) : `~${b.estimated_views.toLocaleString()}`}</strong>
                    </td>
                    <td className="num">{v(b.current_views)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="fine">{fill(p.boostHow, { s: d.sponsors_per_page })}</p>
      </section>
    </div>
  );
}

// ---------------------------------------------------------- page editor
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function PageEditor({ fid, p, canEdit }: { fid: string; p: PortalDict; canEdit: boolean }) {
  const [e, setE] = useState<ProfileEdit | null>(null);
  const [f, setF] = useState<Profile | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    portal
      .profile(fid)
      .then((x) => {
        setE(x);
        setF(x.profile);
      })
      .catch((ex) => setErr((ex as Error).message));
  }, [fid]);
  useEffect(load, [load]);
  if (err && !e) return <p className="form-error">{err}</p>;
  if (!e || !f) return <p className="loading">…</p>;

  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setF({ ...f, [k]: v });
  const toggle = (k: "languages" | "accessibility", v: string) =>
    set(k, f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v]);
  const save = async (submit: boolean) => {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const out = await portal.saveProfile(fid, f, submit);
      setE(out);
      setF(out.profile);
      setMsg(submit ? p.submitted : p.saved);
    } catch (ex) {
      setErr((ex as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const statusLabel = (s: string) => (p as unknown as Record<string, string>)[`st_${s}`] ?? s;

  return (
    <div className="acct-editor">
      <p>
        {p.status}: <span className={`badge st-${e.status}`}>{statusLabel(e.status)}</span>
      </p>
      {e.rejected_note && (
        <p className="notice">
          {p.rejectedNote} {e.rejected_note}
        </p>
      )}
      <fieldset className="card acct-card" disabled={!canEdit}>
        <div className="field">
          <label htmlFor="pf-about">{p.fAbout}</label>
          <textarea id="pf-about" rows={5} maxLength={2000} value={f.about ?? ""} onChange={(x) => set("about", x.target.value)} />
        </div>
        <div className="acct-two">
          <div className="field">
            <label htmlFor="pf-web">{p.fWebsite}</label>
            <input id="pf-web" inputMode="url" value={f.website_url ?? ""} onChange={(x) => set("website_url", x.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="pf-book">{p.fBooking}</label>
            <input id="pf-book" inputMode="url" value={f.booking_url ?? ""} onChange={(x) => set("booking_url", x.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="pf-phone">{p.fPhone}</label>
            <input id="pf-phone" inputMode="tel" value={f.phone ?? ""} onChange={(x) => set("phone", x.target.value)} />
          </div>
        </div>
        <h3>{p.fHours}</h3>
        <div className="hours-edit">
          {DAYS.map((d) => {
            const val = f.hours[d] ?? "closed";
            const open = val !== "closed";
            const [a, b] = open ? val.split("-") : ["09:00", "17:00"];
            const put = (v: string) => set("hours", { ...f.hours, [d]: v });
            return (
              <div key={d} className="hours-row">
                <span className="hours-day">{p.days[d]}</span>
                <label className="check">
                  <input type="checkbox" checked={open} onChange={(x) => put(x.target.checked ? `${a}-${b}` : "closed")} /> {p.fOpen}
                </label>
                {open && (
                  <>
                    <input type="time" aria-label={`${p.days[d]} start`} value={a} onChange={(x) => put(`${x.target.value}-${b}`)} />
                    <span>–</span>
                    <input type="time" aria-label={`${p.days[d]} end`} value={b} onChange={(x) => put(`${a}-${x.target.value}`)} />
                  </>
                )}
              </div>
            );
          })}
        </div>
        <h3>{p.languages}</h3>
        <div className="check-grid">
          {e.languages.map((l) => (
            <label key={l} className="check">
              <input type="checkbox" checked={f.languages.includes(l)} onChange={() => toggle("languages", l)} /> {l}
            </label>
          ))}
        </div>
        <h3>{p.access}</h3>
        <div className="check-grid">
          {e.accessibility.map((a) => (
            <label key={a} className="check">
              <input type="checkbox" checked={f.accessibility.includes(a)} onChange={() => toggle("accessibility", a)} /> {p.accessLabels[a] ?? a}
            </label>
          ))}
        </div>
        <div className="field">
          <label htmlFor="pf-ins">{p.fInsurance}</label>
          <textarea id="pf-ins" rows={2} maxLength={500} value={f.insurance_note ?? ""} onChange={(x) => set("insurance_note", x.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="pf-soc">{p.fSocial}</label>
          <textarea
            id="pf-soc"
            rows={2}
            value={f.social_urls.join("\n")}
            onChange={(x) => set("social_urls", x.target.value.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 6))}
          />
        </div>
        {err && <p className="form-error">{err}</p>}
        {msg && <p className="notice good">{msg}</p>}
        <div className="acct-actions">
          <button type="button" className="btn ghost" disabled={busy} onClick={() => save(false)}>
            {p.saveDraft}
          </button>
          <button type="button" className="btn primary" disabled={busy} onClick={() => save(true)}>
            {p.submit}
          </button>
        </div>
      </fieldset>
      <Images fid={fid} e={e} p={p} canEdit={canEdit} onChange={load} statusLabel={statusLabel} />
    </div>
  );
}

function Images({
  fid,
  e,
  p,
  canEdit,
  onChange,
  statusLabel,
}: {
  fid: string;
  e: ProfileEdit;
  p: PortalDict;
  canEdit: boolean;
  onChange: () => void;
  statusLabel: (s: string) => string;
}) {
  const [kind, setKind] = useState<"logo" | "photo">("photo");
  const [file, setFile] = useState<File | null>(null);
  const [alt, setAlt] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <section className="card acct-card">
      <h2>{p.images}</h2>
      <p className="muted">{p.imagesSub}</p>
      <ul className="media-grid">
        {e.media.map((m) => (
          <li key={m.id}>
            <img src={m.url} alt={m.alt_text ?? ""} />
            <span className={`badge st-${m.status}`}>
              {m.kind === "logo" ? p.logo : p.photo} · {statusLabel(m.status)}
            </span>
            {canEdit && (
              <button type="button" className="link-btn" onClick={() => portal.removeMedia(fid, m.id).then(onChange)}>
                {p.remove}
              </button>
            )}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="upload"
          onSubmit={async (ev) => {
            ev.preventDefault();
            if (!file) return;
            setBusy(true);
            setErr("");
            try {
              await portal.upload(fid, kind, file, alt);
              setFile(null);
              setAlt("");
              (ev.target as HTMLFormElement).reset();
              onChange();
            } catch (ex) {
              setErr((ex as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <div className="segmented">
            {(["logo", "photo"] as const).map((k) => (
              <label key={k} className={kind === k ? "seg on" : "seg"}>
                <input type="radio" name="kind" checked={kind === k} onChange={() => setKind(k)} /> {k === "logo" ? p.logo : p.photo}
              </label>
            ))}
          </div>
          <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(x) => setFile(x.target.files?.[0] ?? null)} />
          <div className="field">
            <label htmlFor="img-alt">{p.alt}</label>
            <input id="img-alt" maxLength={200} value={alt} onChange={(x) => setAlt(x.target.value)} />
          </div>
          {err && <p className="form-error">{err}</p>}
          <button className="btn primary sm" disabled={!file || busy}>
            {p.upload}
          </button>
        </form>
      )}
    </section>
  );
}

// --------------------------------------------------------------- reviews
function ReviewsTab({ fid, p, canEdit }: { fid: string; p: PortalDict; canEdit: boolean }) {
  const [data, setData] = useState<{ summary: { average: string | null; count: number; removed: number }; reviews: ProviderReview[] } | null>(null);
  const [link, setLink] = useState<{ link: string; expires_in_days: number } | null>(null);
  const [copied, setCopied] = useState(false);
  const load = useCallback(() => {
    portal.reviews(fid).then(setData).catch(() => setData(null));
  }, [fid]);
  useEffect(load, [load]);
  return (
    <div className="acct-reviews">
      {canEdit && (
        <section className="card acct-card">
          <h2>{p.inviteTitle}</h2>
          <p className="muted">{p.inviteSub}</p>
          <button
            className="btn primary sm"
            onClick={() => {
              setCopied(false);
              portal.invite(fid).then(setLink);
            }}
          >
            {p.inviteBtn}
          </button>
          {link && (
            <div className="invite-link">
              <input readOnly value={link.link} onFocus={(x) => x.target.select()} aria-label="Review link" />
              <button
                type="button"
                className="btn ghost sm"
                onClick={() => navigator.clipboard?.writeText(link.link).then(() => setCopied(true))}
              >
                {copied ? p.inviteCopied : p.inviteCopy}
              </button>
              <p className="fine">{fill(p.inviteExpires, { n: link.expires_in_days })}</p>
            </div>
          )}
        </section>
      )}
      {data && (
        <section className="card acct-card">
          <h2>
            {p.reviews}
            {data.summary.average && (
              <span className="acct-avg">
                {" "}
                <Stars value={Number(data.summary.average)} /> {data.summary.average} ({data.summary.count})
              </span>
            )}
          </h2>
          {data.summary.removed > 0 && <p className="fine">{fill(p.removedNote, { n: data.summary.removed })}</p>}
          {data.reviews.length === 0 && <p className="muted">{p.noReviews}</p>}
          <ul className="rv-list">
            {data.reviews.map((r) => (
              <ProviderReviewItem key={r.id} r={r} fid={fid} p={p} canEdit={canEdit} onChange={load} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function ProviderReviewItem({
  r,
  fid,
  p,
  canEdit,
  onChange,
}: {
  r: ProviderReview;
  fid: string;
  p: PortalDict;
  canEdit: boolean;
  onChange: () => void;
}) {
  const [mode, setMode] = useState<"" | "reply" | "report">("");
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  return (
    <li className="rv">
      <div className="rv-top">
        <Stars value={r.rating} />
        <span className="rv-name">{r.display_name}</span>
        <span className="rv-date">{r.published_at}</span>
      </div>
      {r.title && <h3 className="rv-title">{r.title}</h3>}
      <p className="rv-body">{r.body}</p>
      <p className="rv-meta">
        <span className="badge">{r.verification === "email" ? p.vEmail : p.vInvite}</span>
      </p>
      {r.reply_body && (
        <div className="rv-reply">
          <strong>{r.reply_status === "published" ? p.reply : p.replyPending}</strong>
          <p>{r.reply_body}</p>
        </div>
      )}
      {note && <p className="notice">{note}</p>}
      {canEdit && mode === "" && (
        <div className="acct-actions">
          <button className="link-btn" onClick={() => setMode("reply")}>
            {p.replyBtn}
          </button>
          <button className="link-btn" onClick={() => setMode("report")}>
            {p.reportBtn}
          </button>
        </div>
      )}
      {mode !== "" && (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              if (mode === "reply") {
                const out = await portal.reply(fid, r.id, text);
                setNote(out.privacy_warning ? p.replyWarn : p.replyPending);
              } else {
                await portal.report(fid, r.id, text);
                setNote(p.reportSent);
              }
              setMode("");
              setText("");
              onChange();
            } catch (ex) {
              setNote((ex as Error).message);
            }
          }}
        >
          <div className="field">
            <label htmlFor={`t-${r.id}`}>{mode === "reply" ? p.replyBtn : p.reportReason}</label>
            <textarea id={`t-${r.id}`} rows={3} maxLength={mode === "reply" ? 1500 : 500} value={text} onChange={(e) => setText(e.target.value)} />
            {mode === "reply" && <p className="fine">{p.replyHint}</p>}
          </div>
          <div className="acct-actions">
            <button className="btn primary sm">{mode === "reply" ? p.replySend : p.reportSend}</button>
            <button type="button" className="btn ghost sm" onClick={() => setMode("")}>
              ×
            </button>
          </div>
        </form>
      )}
    </li>
  );
}


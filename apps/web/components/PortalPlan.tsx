"use client";

// Provider account: listing plan and Sponsored spots (D-051). Listing is free
// for now; this shows that plainly and only offers plans once Cooper sets them.

import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { fill } from "@/lib/i18n";
import { portalText } from "@/lib/i18n_portal";
import { formatMoney } from "@/lib/money";
import { portal, type Billing } from "@/lib/portal";

export function PortalPlan({ fid, isOwner }: { fid: string; isOwner: boolean }) {
  const { lang } = useApp();
  const p = portalText(lang);
  const [b, setB] = useState<Billing | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    portal.billing(fid).then(setB).catch((e) => setErr((e as Error).message));
  }, [fid]);
  if (err) return <p className="form-error">{err}</p>;
  if (!b) return <p className="loading">…</p>;
  const day = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString(lang === "es" ? "es-US" : "en-US", { month: "long", day: "numeric", year: "numeric" });
  const go = (f: () => Promise<{ url: string }>) =>
    f()
      .then((r) => (window.location.href = r.url))
      .catch((e) => setErr((e as Error).message));
  const listing = b.plans.filter((x) => x.kind === "listing");
  const active = b.listing_status === "active" || b.listing_status === "trialing";

  return (
    <div className="acct-plan">
      <section className="card acct-card">
        {!b.fee_starts_on ? (
          <>
            <h2>{p.planFree}</h2>
            <p className="muted">{p.planFreeSub}</p>
          </>
        ) : (
          <>
            <h2>{b.fee_in_force ? fill(p.planFeeOn, { d: day(b.fee_starts_on) }) : fill(p.planFeeSoon, { d: day(b.fee_starts_on) })}</h2>
            {active ? <p className="notice good">{p.planActive}</p> : b.fee_in_force && <p className="notice">{p.planHidden}</p>}
            {!active && listing.length > 0 && (
              <>
                <h3>{p.planChoose}</h3>
                <ul className="plan-list">
                  {listing.map((x) => (
                    <li key={x.code}>
                      <span>
                        <strong>{x.name}</strong> · {fill(p.planPerMonth, { a: formatMoney(x.amount)?.text ?? x.amount })}
                      </span>
                      {isOwner && (
                        <button className="btn primary sm" disabled={!x.can_buy} onClick={() => go(() => portal.checkout(fid, x.code))}>
                          {p.planChoose}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
                {!b.payments_on && <p className="fine">{p.planPaymentsOff}</p>}
              </>
            )}
            {b.listing_status && isOwner && b.payments_on && (
              <button className="btn ghost sm" onClick={() => go(() => portal.billingPortal(fid))}>
                {p.planManage}
              </button>
            )}
          </>
        )}
      </section>
      <section className="card acct-card">
        <h2>{p.planSponsoredTitle}</h2>
        <p className="muted">{fill(p.boostSub, { s: 2 })}</p>
        <p className="notice">{p.planSponsoredOff}</p>
      </section>
    </div>
  );
}

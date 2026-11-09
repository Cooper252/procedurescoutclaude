"use client";

// Prices, specials and packages the provider entered (reviewed by us), shown
// apart from prices in a hospital's own file and labeled (rule 8).

import { useApp } from "@/components/AppState";
import { fill, SERVICE_ES } from "@/lib/i18n";
import { portalText } from "@/lib/i18n_portal";
import { formatMoney, unitLabel } from "@/lib/money";
import type { ProviderPrices as PP } from "@/lib/portal";

function day(iso: string, lang: "en" | "es"): string {
  return new Date(iso + "T12:00:00").toLocaleDateString(lang === "es" ? "es-US" : "en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function ProviderPrices({ data }: { data: PP }) {
  const { lang } = useApp();
  const p = portalText(lang);
  if (data.listings.length === 0 && data.packages.length === 0) return null;
  const m = (v: string) => formatMoney(v)?.text ?? `$${v}`;
  const name = (slug: string | null, n: string | null, code: string | null) =>
    (slug && lang === "es" ? SERVICE_ES[slug] : undefined) ?? n ?? code ?? "";

  return (
    <section className="card ph-prices" id="provider-prices">
      <h2>{p.ppTitle}</h2>
      <p className="fine">{p.ppSub}</p>
      {data.listings.length > 0 && (
        <ul className="pp-list">
          {data.listings.map((l, i) => (
            <li key={i} className="pp-row">
              <div className="pp-name">
                <strong>{name(l.service_slug, l.service_name, l.code)}</strong>
                <span className="muted">
                  {l.quantity > 1 ? fill(p.ppSessions, { n: l.quantity }) : unitLabel(l.unit, lang)}
                  {l.code && l.service_name ? ` · ${l.code}` : ""}
                </span>
              </div>
              <div className="pp-price">
                <span className="price-num">{m(l.regular_price)}</span>
              </div>
              {l.special && (
                <div className="special pp-special">
                  <span className="badge special-tag">{l.special.who === "new_patients" ? p.ppNewPatients : p.ppEveryone}</span>
                  <span>
                    <strong>{m(l.special.price)}</strong>
                    {l.special.percent_off && ` (${l.special.percent_off}% off)`}
                    {l.special.ends_on && <span className="special-meta"> · {fill(p.ppEnds, { d: day(l.special.ends_on, lang) })}</span>}
                    {l.special.terms && <span className="special-meta"> · {l.special.terms}</span>}
                  </span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {data.packages.length > 0 && (
        <>
          <h3>{p.ppPackages}</h3>
          <ul className="pp-list">
            {data.packages.map((k, i) => (
              <li key={i} className="pp-row">
                <div className="pp-name">
                  <strong>{k.name}</strong>
                  <span className="muted">
                    {p.ppIncludes}: {k.items.map((x) => `${x.service_name ?? x.code}${x.quantity > 1 ? ` ×${x.quantity}` : ""}`).join(", ")}
                  </span>
                  {k.description && <span className="muted">{k.description}</span>}
                </div>
                <div className="pp-price">
                  <span className="price-num">{m(k.price)}</span>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

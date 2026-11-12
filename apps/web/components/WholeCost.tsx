"use client";

// "Add up the whole cost" on a result card (Cooper, 2026-11-12: "check boxes for
// each aspect of a procedure like doctor fees, facility fees, anesthesia").
// The pieces come from a reviewed bundle (D-036, D-061); each piece is priced
// only from this place's published prices; a piece it didn't publish is shown
// as not published, never as $0.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { money } from "@/lib/money";
import type { Bundle, Estimate, Mode } from "@/lib/types";
import { useApp } from "./AppState";

export function WholeCost({
  bundle,
  facilityId,
  mode,
  planId,
  insurerId,
}: {
  bundle: Bundle;
  facilityId: string;
  mode: Mode;
  planId: string | null;
  insurerId: string | null;
}) {
  const { t } = useApp();
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string[]>(
    bundle.components.filter((c) => c.requirement !== "required" && c.included_by_default).map((c) => c.component_id),
  );
  const [est, setEst] = useState<Estimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const insurance = mode === "plan" && (planId || insurerId);

  useEffect(() => {
    if (!open) return;
    let live = true;
    setError(null);
    api
      .estimate(bundle.slug, {
        facilityId,
        payment: insurance ? "insurance" : "cash",
        includeOptional: chosen,
        planId,
        payerId: insurerId,
      })
      .then((e) => live && setEst(e))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [open, bundle.slug, facilityId, insurance, planId, insurerId, chosen]);

  const toggle = (id: string) => setChosen((x) => (x.includes(id) ? x.filter((y) => y !== id) : [...x, id]));

  function lineText(id: string): string {
    const ln = est?.lines.find((l) => l.component_id === id);
    if (!ln || !est) return "…";
    if (ln.status === "left_out") return t.wcLeftOut;
    if (ln.status === "priced" && ln.amount) return money(ln.amount);
    if (ln.status === "several_prices" && ln.amounts_published.length) {
      const a = ln.amounts_published;
      return `${money(a[0]!)}–${money(a[a.length - 1]!)}`;
    }
    if (ln.status === "not_a_dollar_amount") return ln.rate ?? t.wcNotDollar;
    return t.wcNotPublished;
  }

  const low = est?.total_low ?? est?.total_of_priced_pieces ?? null;
  const high = est?.total_high ?? low;

  return (
    <div className="whole-cost">
      <button
        type="button"
        className="btn ghost sm"
        aria-expanded={open}
        onClick={() => {
          if (!open) api.visit({ page: "search", lang: "en", event: "whole_cost" });
          setOpen(!open);
        }}
      >
        {t.wcOpen}
      </button>
      {open && (
        <div className="wc-body">
          <p className="wc-intro">{t.wcIntro}</p>
          <ul className="wc-list">
            {bundle.components.map((c) => {
              const required = c.requirement === "required";
              const on = required || chosen.includes(c.component_id);
              return (
                <li key={c.component_id} className={on ? "" : "off"}>
                  <label>
                    <input type="checkbox" checked={on} disabled={required} onChange={() => toggle(c.component_id)} />
                    <span>
                      {c.label}
                      {required && <span className="wc-req"> ({t.wcAlways})</span>}
                    </span>
                  </label>
                  <span className="wc-price">{lineText(c.component_id)}</span>
                </li>
              );
            })}
          </ul>
          {error && <p className="form-error">{error}</p>}
          {est && (
            <div className="wc-total">
              <span>{est.complete ? t.wcTotal : t.wcTotalSoFar}</span>
              <strong>{low ? (high && high !== low ? `${money(low)}–${money(high)}` : money(low)) : "—"}</strong>
            </div>
          )}
          {est && !est.complete && <p className="wc-note">{t.wcIncomplete}</p>}
        </div>
      )}
    </div>
  );
}

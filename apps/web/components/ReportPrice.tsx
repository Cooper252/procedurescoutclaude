"use client";

// "Report a wrong price": anyone can tell us; nothing about the person is stored.

import { useState } from "react";
import { useApp } from "@/components/AppState";
import { portalText } from "@/lib/i18n_portal";
import { portal } from "@/lib/portal";

export function ReportPrice({ facilityId, serviceKey, priceShown }: { facilityId: string; serviceKey?: string; priceShown?: string | null }) {
  const { lang } = useApp();
  const p = portalText(lang);
  const [open, setOpen] = useState(false);
  const [problem, setProblem] = useState("price_different");
  const [details, setDetails] = useState("");
  const [state, setState] = useState<"" | "sending" | "sent">("");
  const [err, setErr] = useState("");
  if (state === "sent") return <p className="notice good report-done">{p.rpThanks}</p>;
  return (
    <div className="report">
      <button type="button" className="link-btn report-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
        {p.rpButton}
      </button>
      {open && (
        <form
          className="report-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setState("sending");
            setErr("");
            try {
              await portal.reportPrice({ facility_id: facilityId, problem, service_key: serviceKey ?? null, price_shown: priceShown ?? null, details: details || null });
              setState("sent");
            } catch (ex) {
              setErr((ex as Error).message);
              setState("");
            }
          }}
        >
          <fieldset>
            <legend>{p.rpWhat}</legend>
            {(["price_different", "not_offered", "closed_or_moved", "insurance_wrong", "other"] as const).map((k) => (
              <label key={k} className="check">
                <input type="radio" name={`rp-${facilityId}`} checked={problem === k} onChange={() => setProblem(k)} /> {p.rpProblems[k]}
              </label>
            ))}
          </fieldset>
          <div className="field">
            <label htmlFor={`rpd-${facilityId}`}>{p.rpDetails}</label>
            <textarea id={`rpd-${facilityId}`} rows={2} maxLength={500} value={details} onChange={(e) => setDetails(e.target.value)} />
          </div>
          <p className="fine">{p.rpPrivacy}</p>
          {err && <p className="form-error">{err}</p>}
          <button className="btn primary sm" disabled={state === "sending"}>
            {p.rpSend}
          </button>
        </form>
      )}
    </div>
  );
}

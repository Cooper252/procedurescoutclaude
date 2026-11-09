"use client";

// Provider account: ask to add a practice that isn't in public records (D-052).

import { useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { portalText } from "@/lib/i18n_portal";
import { portal } from "@/lib/portal";

const FIELDS = ["name", "address_line1", "city", "state_code", "zip5", "phone", "website", "npi"] as const;

export function AddPractice() {
  const { lang } = useApp();
  const p = portalText(lang);
  const [open, setOpen] = useState(false);
  const [types, setTypes] = useState<{ code: string; name: string }[]>([]);
  const [mine, setMine] = useState<{ id: string; name: string; status: string; review_note: string | null }[]>([]);
  const [f, setF] = useState<Record<string, string>>({ provider_type: "" });
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    portal.myListingRequests().then(setMine).catch(() => setMine([]));
  }, []);
  useEffect(() => {
    if (open && types.length === 0) portal.providerTypesAll().then(setTypes).catch(() => setTypes([]));
  }, [open, types.length]);
  const label: Record<string, string> = {
    name: p.addName,
    address_line1: p.addAddress,
    city: p.addCity,
    state_code: p.addState,
    zip5: p.addZip,
    phone: p.fPhone,
    website: p.fWebsite,
    npi: p.addNpi,
  };
  const statusLabel = (s: string) => (s === "pending" ? p.pending : s === "approved" ? p.st_published : p.st_rejected);
  return (
    <div className="add-practice">
      {mine.length > 0 && (
        <>
          <h3>{p.addMine}</h3>
          <ul className="claim-hits">
            {mine.map((m) => (
              <li key={m.id}>
                <span>
                  <strong>{m.name}</strong> <span className="badge">{statusLabel(m.status)}</span>
                  {m.review_note && <span className="muted"> · {m.review_note}</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      <button type="button" className="link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
        {p.addTitle}
      </button>
      {open && (
        <form
          className="price-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setErr("");
            setMsg("");
            try {
              await portal.requestListing(Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v.trim() || null])));
              setMsg(p.addSent);
              setF({ provider_type: "" });
              portal.myListingRequests().then(setMine).catch(() => undefined);
            } catch (ex) {
              setErr((ex as Error).message);
            }
          }}
        >
          <p className="muted">{p.addSub}</p>
          <div className="acct-two">
            {FIELDS.map((k) => (
              <div className="field" key={k}>
                <label htmlFor={`ap-${k}`}>{label[k]}</label>
                <input
                  id={`ap-${k}`}
                  required={["name", "address_line1", "city", "state_code", "zip5"].includes(k)}
                  maxLength={k === "state_code" ? 2 : k === "zip5" ? 5 : k === "npi" ? 10 : 120}
                  value={f[k] ?? ""}
                  onChange={(e) => setF({ ...f, [k]: e.target.value })}
                />
              </div>
            ))}
            <div className="field">
              <label htmlFor="ap-type">{p.addType}</label>
              <select id="ap-type" required value={f.provider_type} onChange={(e) => setF({ ...f, provider_type: e.target.value })}>
                <option value="">—</option>
                {types.map((t) => (
                  <option key={t.code} value={t.code}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {err && <p className="form-error">{err}</p>}
          {msg && <p className="notice good">{msg}</p>}
          <button className="btn primary">{p.addSend}</button>
        </form>
      )}
    </div>
  );
}

"use client";

// Provider portal: regular prices (standard service or billing code, sessions),
// specials and packages. Everything is reviewed before it shows.

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/AppState";
import { api } from "@/lib/api";
import { fill } from "@/lib/i18n";
import { portalText, type PortalDict } from "@/lib/i18n_portal";
import { formatMoney } from "@/lib/money";
import { portal, type MyListing, type MyPrices } from "@/lib/portal";
import type { Service } from "@/lib/types";

const SYSTEMS = ["CPT", "HCPCS", "CDT", "MS_DRG"];
const m = (v: string | null) => (v ? formatMoney(v)?.text ?? `$${v}` : "");

function statusBadge(p: PortalDict, s: string) {
  const label = (p as unknown as Record<string, string>)[`st_${s === "draft" ? "rejected" : s}`] ?? s;
  return <span className={`badge st-${s === "draft" ? "rejected" : s}`}>{label}</span>;
}

export function PortalPrices({ fid, canEdit }: { fid: string; canEdit: boolean }) {
  const { lang } = useApp();
  const p = portalText(lang);
  const [data, setData] = useState<MyPrices | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const load = useCallback(() => {
    portal.myPrices(fid).then(setData).catch(() => setData({ listings: [], packages: [] }));
  }, [fid]);
  useEffect(load, [load]);
  useEffect(() => {
    api.services().then(setServices).catch(() => setServices([]));
  }, []);

  return (
    <div className="acct-prices">
      {canEdit && <AddPrice fid={fid} p={p} services={services} onSaved={load} />}
      <section className="card acct-card">
        <h2>{p.prTitle}</h2>
        {!data ? (
          <p className="loading">…</p>
        ) : data.listings.length === 0 ? (
          <p className="muted">{p.prNone}</p>
        ) : (
          <ul className="my-prices">
            {data.listings.map((l) => (
              <Listing key={l.id} l={l} fid={fid} p={p} canEdit={canEdit} onChange={load} />
            ))}
          </ul>
        )}
      </section>
      <Packages fid={fid} p={p} data={data} services={services} canEdit={canEdit} onChange={load} />
    </div>
  );
}

function AddPrice({ fid, p, services, onSaved }: { fid: string; p: PortalDict; services: Service[]; onSaved: () => void }) {
  const [slug, setSlug] = useState("");
  const [system, setSystem] = useState("CPT");
  const [code, setCode] = useState("");
  const [qty, setQty] = useState(1);
  const [price, setPrice] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  return (
    <section className="card acct-card">
      <h2>{p.prAdd}</h2>
      <p className="muted">{p.prSub}</p>
      <form
        className="price-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setErr("");
          setMsg("");
          try {
            await portal.savePrice(fid, {
              service_slug: slug || null,
              code_system: slug ? null : system,
              code: slug ? null : code,
              quantity: qty,
              regular_price: price,
            });
            setMsg(p.prAdded);
            setPrice("");
            onSaved();
          } catch (ex) {
            setErr((ex as Error).message);
          }
        }}
      >
        <div className="field">
          <label htmlFor="pr-svc">{p.prService}</label>
          <select id="pr-svc" value={slug} onChange={(e) => setSlug(e.target.value)}>
            <option value="">—</option>
            {services.map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        {!slug && (
          <div className="price-code">
            <span className="muted">{p.prOr}</span>
            <div className="field">
              <label htmlFor="pr-sys">{p.prSystem}</label>
              <select id="pr-sys" value={system} onChange={(e) => setSystem(e.target.value)}>
                {SYSTEMS.map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", "-")}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="pr-code">{p.prCode}</label>
              <input id="pr-code" maxLength={12} value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} />
            </div>
          </div>
        )}
        <div className="acct-two">
          <div className="field">
            <label htmlFor="pr-qty">{p.prQty}</label>
            <input id="pr-qty" type="number" min={1} max={100} value={qty} onChange={(e) => setQty(Number(e.target.value) || 1)} />
          </div>
          <div className="field">
            <label htmlFor="pr-price">{p.prPrice}</label>
            <input id="pr-price" inputMode="decimal" required value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
        </div>
        {err && <p className="form-error">{err}</p>}
        {msg && <p className="notice good">{msg}</p>}
        <button className="btn primary">{p.prAdd}</button>
      </form>
    </section>
  );
}

function Listing({ l, fid, p, canEdit, onChange }: { l: MyListing; fid: string; p: PortalDict; canEdit: boolean; onChange: () => void }) {
  const [mode, setMode] = useState<"" | "edit" | "special">("");
  const [price, setPrice] = useState(l.regular_price);
  const [kind, setKind] = useState("special_price");
  const [who, setWho] = useState("new_patients");
  const [value, setValue] = useState("");
  const [starts, setStarts] = useState(new Date().toISOString().slice(0, 10));
  const [ends, setEnds] = useState("");
  const [terms, setTerms] = useState("");
  const [err, setErr] = useState("");
  const name = l.service_name ?? `${l.code_system} ${l.code}`;
  const run = async (f: () => Promise<unknown>) => {
    setErr("");
    try {
      await f();
      setMode("");
      onChange();
    } catch (ex) {
      setErr((ex as Error).message);
    }
  };
  return (
    <li className="my-price">
      <div className="my-price-top">
        <div>
          <strong>{name}</strong>
          {l.quantity > 1 && <span className="muted"> · {fill(p.ppSessions, { n: l.quantity })}</span>}
          <div>{statusBadge(p, l.status)}</div>
        </div>
        <div className="my-price-amt">
          <span className="price-num">{m(l.regular_price)}</span>
          {l.proposed_price && <span className="badge st-pending_review">{fill(p.prChangeTo, { p: m(l.proposed_price) })}</span>}
        </div>
      </div>
      {l.review_note && <p className="notice">{p.rejectedNote} {l.review_note}</p>}
      {l.offers.length > 0 && (
        <ul className="my-offers">
          {l.offers.map((o) => (
            <li key={o.id}>
              <span className="badge special-tag">{o.who === "new_patients" ? p.ppNewPatients : p.ppEveryone}</span>{" "}
              {o.kind === "special_price" ? m(o.offer_price) : o.kind === "percent_off" ? `${o.percent_off}%` : `−${m(o.amount_off)}`} · {o.starts_on}
              {o.ends_on ? ` → ${o.ends_on}` : ""} {statusBadge(p, o.status)}
              {canEdit && (
                <button className="link-btn" onClick={() => run(() => portal.withdrawSpecial(fid, o.id))}>
                  {p.prWithdraw}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && mode === "" && (
        <div className="acct-actions">
          <button className="link-btn" onClick={() => setMode("edit")}>
            {p.prEdit}
          </button>
          <button className="link-btn" onClick={() => setMode("special")}>
            {p.prAddSpecial}
          </button>
          <button className="link-btn danger" onClick={() => run(() => portal.withdrawPrice(fid, l.id))}>
            {p.prWithdraw}
          </button>
        </div>
      )}
      {mode === "edit" && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            run(() =>
              portal.savePrice(fid, {
                service_slug: l.service_slug,
                code_system: l.service_slug ? null : l.code_system,
                code: l.service_slug ? null : l.code,
                quantity: l.quantity,
                regular_price: price,
              }),
            );
          }}
        >
          <div className="field">
            <label htmlFor={`e-${l.id}`}>{p.prPrice}</label>
            <input id={`e-${l.id}`} inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
          </div>
          <button className="btn primary sm">{p.prAdd}</button>
          <button type="button" className="btn ghost sm" onClick={() => setMode("")}>
            ×
          </button>
        </form>
      )}
      {mode === "special" && (
        <form
          className="special-form"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => portal.addSpecial(fid, l.id, { kind, who, value, starts_on: starts, ends_on: ends || null, terms: terms || null }));
          }}
        >
          <p className="fine">{p.prSpecialRule}</p>
          <div className="acct-two">
            <div className="field">
              <label htmlFor={`k-${l.id}`}>{p.prKind}</label>
              <select id={`k-${l.id}`} value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="special_price">{p.kSpecial}</option>
                <option value="percent_off">{p.kPercent}</option>
                <option value="amount_off">{p.kAmount}</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor={`v-${l.id}`}>{p.prValue}</label>
              <input id={`v-${l.id}`} inputMode="decimal" required value={value} onChange={(e) => setValue(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor={`w-${l.id}`}>{p.prWho}</label>
              <select id={`w-${l.id}`} value={who} onChange={(e) => setWho(e.target.value)}>
                <option value="new_patients">{p.ppNewPatients}</option>
                <option value="everyone">{p.ppEveryone}</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor={`s-${l.id}`}>{p.prStarts}</label>
              <input id={`s-${l.id}`} type="date" value={starts} onChange={(e) => setStarts(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor={`n-${l.id}`}>{p.prEnds}</label>
              <input id={`n-${l.id}`} type="date" value={ends} onChange={(e) => setEnds(e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label htmlFor={`t-${l.id}`}>{p.prTerms}</label>
            <input id={`t-${l.id}`} maxLength={300} value={terms} onChange={(e) => setTerms(e.target.value)} />
          </div>
          <div className="acct-actions">
            <button className="btn primary sm">{p.prAddSpecial}</button>
            <button type="button" className="btn ghost sm" onClick={() => setMode("")}>
              ×
            </button>
          </div>
        </form>
      )}
      {err && <p className="form-error">{err}</p>}
    </li>
  );
}

type Piece = { slug: string; qty: number };

function Packages({
  fid,
  p,
  data,
  services,
  canEdit,
  onChange,
}: {
  fid: string;
  p: PortalDict;
  data: MyPrices | null;
  services: Service[];
  canEdit: boolean;
  onChange: () => void;
}) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [price, setPrice] = useState("");
  const [pieces, setPieces] = useState<Piece[]>([{ slug: "", qty: 1 }]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  return (
    <section className="card acct-card">
      <h2>{p.pkTitle}</h2>
      <p className="muted">{p.pkSub}</p>
      {data && data.packages.length > 0 && (
        <ul className="my-prices">
          {data.packages.map((k) => (
            <li key={k.id} className="my-price">
              <div className="my-price-top">
                <div>
                  <strong>{k.name}</strong>
                  <div className="muted">{k.items.map((x) => `${x.service_name ?? x.code}${x.quantity > 1 ? ` ×${x.quantity}` : ""}`).join(", ")}</div>
                  <div>{statusBadge(p, k.status)}</div>
                </div>
                <span className="price-num">{m(k.price)}</span>
              </div>
              {k.review_note && <p className="notice">{p.rejectedNote} {k.review_note}</p>}
              {canEdit && (
                <button className="link-btn danger" onClick={() => portal.withdrawPackage(fid, k.id).then(onChange)}>
                  {p.prWithdraw}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form
          className="price-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setErr("");
            setMsg("");
            try {
              await portal.addPackage(fid, {
                name,
                description: desc || null,
                price,
                items: pieces.filter((x) => x.slug).map((x) => ({ service_slug: x.slug, quantity: x.qty })),
              });
              setMsg(p.prAdded);
              setName("");
              setDesc("");
              setPrice("");
              setPieces([{ slug: "", qty: 1 }]);
              onChange();
            } catch (ex) {
              setErr((ex as Error).message);
            }
          }}
        >
          <div className="acct-two">
            <div className="field">
              <label htmlFor="pk-name">{p.pkName}</label>
              <input id="pk-name" maxLength={80} required value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="pk-price">{p.pkPrice}</label>
              <input id="pk-price" inputMode="decimal" required value={price} onChange={(e) => setPrice(e.target.value)} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="pk-desc">{p.pkDesc}</label>
            <input id="pk-desc" maxLength={500} value={desc} onChange={(e) => setDesc(e.target.value)} />
          </div>
          <fieldset className="pk-pieces">
            <legend>{p.pkPieces}</legend>
            {pieces.map((x, i) => (
              <div key={i} className="pk-piece">
                <select
                  aria-label={p.prService}
                  value={x.slug}
                  onChange={(e) => setPieces(pieces.map((y, j) => (j === i ? { ...y, slug: e.target.value } : y)))}
                >
                  <option value="">—</option>
                  {services.map((s) => (
                    <option key={s.slug} value={s.slug}>
                      {s.name}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  max={100}
                  aria-label={p.prQty}
                  value={x.qty}
                  onChange={(e) => setPieces(pieces.map((y, j) => (j === i ? { ...y, qty: Number(e.target.value) || 1 } : y)))}
                />
              </div>
            ))}
            {pieces.length < 12 && (
              <button type="button" className="link-btn" onClick={() => setPieces([...pieces, { slug: "", qty: 1 }])}>
                + {p.pkAddPiece}
              </button>
            )}
          </fieldset>
          {err && <p className="form-error">{err}</p>}
          {msg && <p className="notice good">{msg}</p>}
          <button className="btn primary">{p.pkSave}</button>
        </form>
      )}
    </section>
  );
}

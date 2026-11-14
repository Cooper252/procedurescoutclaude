"use client";

// One price list for everything a person needs (Cooper, 2026-11-14: "Almost
// like an à la carte price list once they select the main procedure"). The
// chosen pieces are at the top (remove any, add more); below, each place
// shows every piece's price and the total of those prices. A total appears
// only when the place published a dollar price for every piece; otherwise the
// missing pieces say "Not published". Nothing is estimated or substituted.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppState";
import { InsurancePicker, type Insurance } from "@/components/InsurancePicker";
import { OptionPicker, optionNames } from "@/components/OptionPicker";
import { api } from "@/lib/api";
import { fill } from "@/lib/i18n";
import { compareDecimal, money } from "@/lib/money";
import { itemHref, listHref, parseItem, placeTotal, type Line } from "@/lib/priceList";
import type { Mode, Options, Plan, SearchResult } from "@/lib/types";

const MAX_ITEMS = 8;

export default function PriceListPage() {
  return (
    <Suspense fallback={<div className="wrap page"><p className="loading">…</p></div>}>
      <PriceList />
    </Suspense>
  );
}

type Row = {
  facility_id: string;
  name: string;
  city: string | null;
  distance: string;
  lines: Line[];
};

function PriceList() {
  const { t, lang, setPlace } = useApp();
  const router = useRouter();
  const sp = useSearchParams();
  const items = useMemo(() => sp.getAll("i").filter((k) => parseItem(k)).slice(0, MAX_ITEMS), [sp]);
  const q = (sp.get("q") ?? "").trim();
  const zip = sp.get("zip");
  const latParam = sp.get("lat");
  const lngParam = sp.get("lng");
  const radius = sp.get("r") ?? "25";
  const ptype = sp.get("type");
  const online = sp.get("online") === "1";
  const mode = (sp.get("mode") === "plan" ? "plan" : "cash") as Mode;
  const planId = sp.get("plan");
  const payerRaw = sp.get("payer");
  const insurerId = sp.get("insurer");

  const [coords, setCoords] = useState<{ lat: string; lng: string } | null>(
    latParam && lngParam ? { lat: latParam, lng: lngParam } : null,
  );
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, SearchResult | null>>({});
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(sp.get("add") === "1" || items.length === 0);
  const [addText, setAddText] = useState(q);
  const [addQ, setAddQ] = useState(q);
  const [addData, setAddData] = useState<Options | null>(null);
  const [baseData, setBaseData] = useState<Options | null>(null);
  const [plans, setPlans] = useState<Plan[] | null>(null);

  function go(nextItems: string[], changes: Record<string, string | null> = {}) {
    const p = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(changes)) (v === null ? p.delete(k) : p.set(k, v));
    router.replace(listHref(nextItems, p), { scroll: false });
  }

  useEffect(() => {
    if (latParam && lngParam) {
      setCoords({ lat: latParam, lng: lngParam });
      return;
    }
    if (!zip) return;
    api
      .zip(zip)
      .then((p) => {
        setPlace(p);
        setCoords({ lat: p.lat, lng: p.lng });
      })
      .catch(() => setError(t.zipNotFound));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zip, latParam, lngParam]);

  // names for the chosen pieces, from the options list of the words searched
  useEffect(() => {
    if (q.length < 2) return;
    api.options(q).then(setBaseData).catch(() => setBaseData(null));
  }, [q]);
  useEffect(() => {
    if (addQ.trim().length < 2) return;
    let live = true;
    api
      .options(addQ.trim())
      .then((d) => live && setAddData(d))
      .catch(() => live && setAddData(null));
    return () => {
      live = false;
    };
  }, [addQ]);

  useEffect(() => {
    if (mode === "plan" && plans === null) api.plans().then(setPlans).catch(() => setPlans([]));
  }, [mode, plans]);
  const chosen: Insurance | null =
    mode !== "plan"
      ? null
      : planId
        ? (() => {
            const p = plans?.find((x) => x.plan_id === planId);
            return { plan: planId, label: p ? `${p.payer} · ${p.plan}` : "" };
          })()
        : insurerId
          ? (() => {
              const p = plans?.find((x) => x.payer_id === insurerId);
              return { insurer: insurerId, label: p ? t.insUnsureLabel.replace("{payer}", p.payer) : "" };
            })()
          : payerRaw
            ? { payer: payerRaw, label: payerRaw }
            : null;
  const needsInsurance = mode === "plan" && !planId && !payerRaw && !insurerId;

  const itemsKey = items.join("|");
  useEffect(() => {
    if (!coords || !items.length || needsInsurance) {
      setResults({});
      return;
    }
    let live = true;
    setLoading(true);
    setError(null);
    Promise.all(
      items.map((k) => {
        const it = parseItem(k)!;
        return api
          .search({
            lat: coords.lat,
            lng: coords.lng,
            service: it.kind === "service" ? it.slug : "",
            codeSystem: it.kind === "code" ? it.system : null,
            code: it.kind === "code" ? it.code : null,
            mode,
            planId,
            payerRaw,
            insurerId,
            providerType: ptype,
            radius,
            online,
          })
          .then((r) => [k, r] as const)
          .catch(() => [k, null] as const);
      }),
    )
      .then((pairs) => live && setResults(Object.fromEntries(pairs)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coords, itemsKey, mode, planId, payerRaw, insurerId, ptype, radius, online, needsInsurance]);

  const names: Record<string, string> = { ...optionNames(addData, lang), ...optionNames(baseData, lang) };
  const nameOf = (k: string) => {
    if (names[k]) return names[k]!;
    const r = results[k];
    const it = parseItem(k);
    if (r?.service_name && it?.kind === "service") return r.service_name;
    if (it?.kind === "code") return r?.code_description ? `${r.code_description} (${it.system} ${it.code})` : `${it.system} ${it.code}`;
    return k;
  };

  // every place, with each piece's price there
  const { complete, partial, failedItems } = useMemo(() => {
    const byPlace = new Map<string, Row>();
    const failed: string[] = [];
    for (const k of items) {
      const r = results[k];
      if (r === null) failed.push(k);
      if (!r) continue;
      for (const f of r.facilities) {
        const row = byPlace.get(f.facility_id) ?? {
          facility_id: f.facility_id,
          name: f.name,
          city: f.city,
          distance: f.distance_miles,
          lines: [],
        };
        byPlace.set(f.facility_id, row);
      }
    }
    for (const row of byPlace.values()) {
      row.lines = items.map((k) => {
        const f = results[k]?.facilities.find((x) => x.facility_id === row.facility_id);
        const priced = f && f.status === "prices" && f.headline;
        return {
          key: k,
          low: priced ? f!.headline : null,
          high: priced ? f!.headline_highest ?? null : null,
          ratesOnly: Boolean(f?.plan_rates_only),
          pricedAs: priced && f?.priced_as?.length ? f.priced_as : undefined,
        };
      });
    }
    const rows = [...byPlace.values()].filter((r) => r.lines.some((l) => l.low !== null));
    const full = rows
      .map((r) => ({ r, total: placeTotal(r.lines) }))
      .filter((x) => x.total)
      .sort((a, b) => compareDecimal(a.total!.low, b.total!.low) || compareDecimal(a.r.distance, b.r.distance));
    const part = rows
      .filter((r) => !placeTotal(r.lines))
      .sort(
        (a, b) =>
          b.lines.filter((l) => l.low).length - a.lines.filter((l) => l.low).length || compareDecimal(a.distance, b.distance),
      );
    return { complete: full, partial: part, failedItems: failed };
  }, [results, itemsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const where = zip ?? (coords ? t.useLocation.toLowerCase() : "");

  function PlaceCard({ r, total }: { r: Row; total: { low: string; high: string } | null }) {
    return (
      <li className="card list-place">
        <div className="list-place-head">
          <Link className="result-name" href={`/facility/${r.facility_id}`}>
            {r.name}
          </Link>
          <span className="fine">
            {[r.city, `${r.distance} mi`].filter(Boolean).join(" · ")}
          </span>
        </div>
        {total ? (
          <p className="list-total">
            <span className="list-total-label">{fill(t.listTotal, { n: String(items.length) })}</span>
            <strong>{total.low === total.high ? money(total.low) : `${money(total.low)} – ${money(total.high)}`}</strong>
          </p>
        ) : (
          <p className="list-missing">{t.listNoTotal}</p>
        )}
        <ul className="list-lines">
          {r.lines.map((l) => (
            <li key={l.key} className={l.low ? "" : "missing"}>
              <span className="list-line-name">
                {nameOf(l.key)}
                {l.pricedAs && <span className="list-line-as">{fill(t.listPricedAs, { codes: l.pricedAs.join(", ") })}</span>}
              </span>
              <span className="list-line-price">
                {l.low
                  ? l.high && l.high !== l.low
                    ? `${money(l.low)} – ${money(l.high)}`
                    : money(l.low)
                  : l.ratesOnly && mode === "cash"
                    ? t.listRatesOnly
                    : t.listNotPublished}
              </span>
            </li>
          ))}
        </ul>
      </li>
    );
  }

  return (
    <div className="results-page price-list">
      <div className="results-head">
        <div className="wrap">
          <p className="eyebrow">{t.listEyebrow}</p>
          <h1 className="list-title">{q ? fill(t.listTitle, { q }) : t.listEyebrow}</h1>
          <p className="results-where">
            {online ? t.onlineWhere : where ? <>{t.near} <strong>{where}</strong> · {radius} mi</> : null}
          </p>
          <ul className="list-chips" aria-label={t.listChosen}>
            {items.map((k) => (
              <li key={k} className="chip">
                <span>{nameOf(k)}</span>
                <button type="button" aria-label={fill(t.listRemove, { what: nameOf(k) })} onClick={() => go(items.filter((x) => x !== k))}>
                  ×
                </button>
              </li>
            ))}
            <li>
              <button type="button" className="btn ghost sm list-add" onClick={() => setAdding((a) => !a)} aria-expanded={adding}>
                {adding ? t.listDoneAdding : t.listAdd}
              </button>
            </li>
          </ul>
          <div className="segmented two list-mode" role="radiogroup" aria-label={t.payingHow}>
            <button type="button" role="radio" aria-checked={mode === "cash"} className={mode === "cash" ? "seg on" : "seg"} onClick={() => go(items, { mode: null, plan: null, payer: null, insurer: null })}>
              {t.modeCash}
            </button>
            <button type="button" role="radio" aria-checked={mode === "plan"} className={mode === "plan" ? "seg on" : "seg"} onClick={() => go(items, { mode: "plan" })}>
              {t.modePlan}
            </button>
          </div>
          {mode === "plan" && (
            <div className="list-insurance">
              <InsurancePicker
                id="list-ins"
                value={chosen}
                near={coords}
                onChange={(v) => {
                  if (!v) return;
                  go(items, {
                    mode: "plan",
                    plan: "plan" in v ? v.plan : null,
                    insurer: "insurer" in v ? v.insurer : null,
                    payer: "payer" in v ? v.payer : null,
                  });
                }}
              />
            </div>
          )}
        </div>
      </div>
      <div className="wrap page">
        {adding && (
          <section className="card list-adder">
            <form
              className="list-add-search"
              onSubmit={(e) => {
                e.preventDefault();
                setAddQ(addText);
              }}
            >
              <label htmlFor="list-add-q">{t.listAddSearch}</label>
              <div className="list-add-row">
                <input id="list-add-q" value={addText} placeholder={t.whatPlaceholder} onChange={(e) => setAddText(e.target.value)} />
                <button type="submit" className="btn primary sm">
                  {t.listFind}
                </button>
              </div>
            </form>
            {addData && (
              <OptionPicker
                data={addData}
                selected={items}
                onChange={(next) => go(next.slice(0, MAX_ITEMS))}
                priceHref={(k) => itemHref(k, new URLSearchParams(sp.toString()))}
              />
            )}
            {items.length >= MAX_ITEMS && <p className="fine">{fill(t.listMax, { n: String(MAX_ITEMS) })}</p>}
          </section>
        )}
        {!coords && !error && <p className="notice">{t.listNeedZip}</p>}
        {error && <p className="form-error">{error}</p>}
        {needsInsurance && <p className="notice">{t.insurerPick}</p>}
        {items.length === 0 && <p className="notice">{t.listEmpty}</p>}
        {loading && <p className="loading">…</p>}
        {!loading && items.length > 0 && coords && !needsInsurance && (
          <>
            <p className="fine list-explain">{t.listExplain}</p>
            {failedItems.length > 0 && (
              <p className="notice">{fill(t.listFailed, { what: failedItems.map(nameOf).join(", ") })}</p>
            )}
            {complete.length === 0 && partial.length === 0 && <p className="notice">{t.listNone}</p>}
            {complete.length > 0 && (
              <section>
                <h2 className="list-section">{fill(t.listCompleteHead, { n: String(complete.length) })}</h2>
                <ul className="list-places">
                  {complete.map((x) => (
                    <PlaceCard key={x.r.facility_id} r={x.r} total={x.total} />
                  ))}
                </ul>
              </section>
            )}
            {partial.length > 0 && (
              <section>
                <h2 className="list-section">{fill(t.listPartialHead, { n: String(partial.length) })}</h2>
                <ul className="list-places">
                  {partial.map((r) => (
                    <PlaceCard key={r.facility_id} r={r} total={null} />
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

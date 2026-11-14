"use client";

// Every published price option for what a person typed (Cooper, 2026-11-14:
// "I don't want 2 options, I want 20 options if that's what there is").
// The person ticks what they need (a hospital stay, anesthesia, the doctor,
// newborn care...) and sees one price list for all of it at each place.
// Each option keeps its own code; nothing is merged.

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppState";
import { OptionPicker, optionNames } from "@/components/OptionPicker";
import { PageIntro } from "@/components/PageIntro";
import { api } from "@/lib/api";
import { fill } from "@/lib/i18n";
import { itemHref, listHref } from "@/lib/priceList";
import type { Options } from "@/lib/types";

export default function OptionsPage() {
  return (
    <Suspense fallback={<div className="wrap page"><p className="loading">…</p></div>}>
      <AllOptions />
    </Suspense>
  );
}

function AllOptions() {
  const { t, lang, place } = useApp();
  const router = useRouter();
  const sp = useSearchParams();
  const q = (sp.get("q") ?? "").trim();
  const [data, setData] = useState<Options | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string[]>(sp.getAll("i"));
  const [zip, setZip] = useState(sp.get("zip") ?? place?.zip ?? "");
  const hasLatLng = Boolean(sp.get("lat") && sp.get("lng"));

  useEffect(() => {
    if (q.length < 2) return;
    let live = true;
    setData(null);
    setFailed(false);
    api
      .options(q)
      .then((d) => live && setData(d))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [q]);

  // where / how paying, carried into the price list
  const rest = useMemo(() => {
    const p = new URLSearchParams(sp.toString());
    p.delete("i");
    if (!hasLatLng) {
      if (/^\d{5}$/.test(zip)) p.set("zip", zip);
      else p.delete("zip");
    }
    return p;
  }, [sp, zip, hasLatLng]);

  const ready = /^\d{5}$/.test(zip) || hasLatLng;
  const names = optionNames(data, lang);

  return (
    <>
      <PageIntro
        eyebrow={t.optionsEyebrow}
        title={q ? fill(t.optionsTitle, { q }) : t.optionsEyebrow}
        lead={data && data.total > 0 ? fill(t.optionsLead, { n: String(data.total) }) : undefined}
      />
      <div className="wrap page options-page">
        {failed && <p className="notice">{fill(t.optionsNone, { q })}</p>}
        {!data && !failed && q.length >= 2 && <p className="loading">…</p>}
        {data && data.total === 0 && data.services.length === 0 && <p className="notice">{fill(t.optionsNone, { q })}</p>}
        {data && (data.total > 0 || data.services.length > 0) && (
          <>
            {!hasLatLng && (
              <div className="options-tools one">
                <label className="field options-zip">
                  <span>{t.optionsZipLabel}</span>
                  <input
                    inputMode="numeric"
                    autoComplete="postal-code"
                    maxLength={5}
                    value={zip}
                    placeholder={t.wherePlaceholder}
                    onChange={(e) => setZip(e.target.value.replace(/\D/g, ""))}
                  />
                </label>
              </div>
            )}
            <p className="pick-intro">{t.pickIntro}</p>
            <OptionPicker
              data={data}
              selected={selected}
              onChange={setSelected}
              priceHref={(k) => (ready ? itemHref(k, rest) : null)}
            />
            <div className="pick-bar" role="region" aria-label={t.pickBarLabel}>
              <div className="wrap pick-bar-in">
                <span className="pick-bar-count">
                  {selected.length === 0
                    ? t.pickNone
                    : selected.length === 1
                      ? t.pickOne
                      : fill(t.pickMany, { n: String(selected.length) })}
                  {selected.length > 0 && (
                    <span className="pick-bar-names">{selected.map((k) => names[k] ?? k).join(" · ")}</span>
                  )}
                </span>
                <button
                  type="button"
                  className="btn primary"
                  disabled={selected.length === 0 || !ready}
                  onClick={() => router.push(listHref(selected, rest))}
                >
                  {ready ? t.pickSee : t.pickNeedZip}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

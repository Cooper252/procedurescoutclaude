"use client";

// Every published price option for what a person typed (Cooper, 2026-11-14:
// "I don't want 2 options, I want 20 options if that's what there is").
// Grouped by kind (hospital stays, anesthesia, surgery, imaging, ...), most
// widely published first. Each option keeps its own code; nothing is merged.

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useApp } from "@/components/AppState";
import { PageIntro } from "@/components/PageIntro";
import { api } from "@/lib/api";
import { fill, SERVICE_ES } from "@/lib/i18n";
import type { CodeOption, Options } from "@/lib/types";

const FIRST = 8;

export default function OptionsPage() {
  return (
    <Suspense fallback={<div className="wrap page"><p className="loading">…</p></div>}>
      <AllOptions />
    </Suspense>
  );
}

function AllOptions() {
  const { t, lang, place } = useApp();
  const sp = useSearchParams();
  const q = (sp.get("q") ?? "").trim();
  const [data, setData] = useState<Options | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
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

  // where / how paying, carried into each option's price search
  const rest = useMemo(() => {
    const p = new URLSearchParams(sp.toString());
    p.delete("q");
    if (!hasLatLng) {
      if (/^\d{5}$/.test(zip)) p.set("zip", zip);
      else p.delete("zip");
    }
    return p;
  }, [sp, zip, hasLatLng]);

  const href = (o: { service?: string | null; code_system?: string | null; code?: string | null; slug?: string }) => {
    const p = new URLSearchParams(rest.toString());
    if (o.code_system && o.code) {
      p.set("code_system", o.code_system);
      p.set("code", o.code);
    } else if (o.slug) p.set("service", o.slug);
    return `/search?${p.toString()}`;
  };

  const needle = filter.trim().toLowerCase();
  const shown = (o: CodeOption) =>
    !needle ||
    o.name.toLowerCase().includes(needle) ||
    (o.wording ?? "").toLowerCase().includes(needle) ||
    `${o.code_system} ${o.code}`.toLowerCase().includes(needle);

  const ready = /^\d{5}$/.test(zip) || hasLatLng;
  const label = (slug: string, name: string) => (lang === "es" ? SERVICE_ES[slug] ?? name : name);
  const groupLabel = (g: string) => (t as unknown as Record<string, string>)[`optionGroup_${g}`] ?? g;

  return (
    <>
      <PageIntro
        eyebrow={t.optionsEyebrow}
        title={q ? fill(t.optionsTitle, { q }) : t.optionsEyebrow}
        lead={data && data.total > 0 ? fill(t.optionsLead, { n: String(data.total) }) : undefined}
      />
      <div className="wrap page options-page">
        {failed && <p className="notice">{t.optionsNone.replace("{q}", q)}</p>}
        {!data && !failed && q.length >= 2 && <p className="loading">…</p>}
        {data && data.total === 0 && data.services.length === 0 && (
          <p className="notice">{fill(t.optionsNone, { q })}</p>
        )}
        {data && (data.total > 0 || data.services.length > 0) && (
          <>
            <div className="options-tools">
              {!hasLatLng && (
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
              )}
              <label className="field options-filter">
                <span>{t.optionsFilter}</span>
                <input value={filter} placeholder={t.optionsFilterPh} onChange={(e) => setFilter(e.target.value)} />
              </label>
            </div>
            <p className="fine options-how">{t.optionsHowTo}</p>
            {data.services.length > 0 && !needle && (
              <section className="options-group">
                <h2>
                  {t.optionsServices} <span className="options-count">{data.services.length}</span>
                </h2>
                <ul className="options-list">
                  {data.services.map((s) => (
                    <li key={s.slug}>
                      <Link className={ready ? "option" : "option off"} href={ready ? href({ slug: s.slug }) : "#"} aria-disabled={!ready}>
                        <span className="option-name">{label(s.slug, s.name)}</span>
                        {s.about && <span className="option-wording">{s.about}</span>}
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {data.groups.map((g) => {
              const items = g.options.filter(shown);
              if (!items.length) return null;
              const all = openGroups[g.group] || Boolean(needle);
              const list = all ? items : items.slice(0, FIRST);
              return (
                <section key={g.group} className="options-group">
                  <h2>
                    {groupLabel(g.group)} <span className="options-count">{items.length}</span>
                  </h2>
                  <ul className="options-list">
                    {list.map((o) => (
                      <li key={`${o.code_system}:${o.code}`}>
                        <Link className={ready ? "option" : "option off"} href={ready ? href(o) : "#"} aria-disabled={!ready}>
                          <span className="option-name">{o.service ? label(o.service, o.name) : o.name}</span>
                          {o.wording && (
                            <span className="option-wording">
                              {t.theirWording}: “{o.wording}”
                            </span>
                          )}
                          <span className="option-meta">
                            <span className="option-code">
                              {o.code_system} {o.code}
                            </span>
                            <span>{o.places === 1 ? t.optionsPlaces1 : fill(t.optionsPlaces, { n: String(o.places) })}</span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                  {items.length > FIRST && !needle && (
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => setOpenGroups((s) => ({ ...s, [g.group]: !s[g.group] }))}
                    >
                      {all ? t.optionsShowFewer : fill(t.optionsShowAll, { n: String(items.length) })}
                    </button>
                  )}
                </section>
              );
            })}
          </>
        )}
      </div>
    </>
  );
}

"use client";

// A checklist of every published option for what was typed (Cooper,
// 2026-11-14: "an à la carte price list once they select the main
// procedure"). Hospital stays are pick-one (a person has one stay); everything
// else can be added. Used on the all-options page and the price-list page.

import Link from "next/link";
import { useState } from "react";
import { fill, SERVICE_ES } from "@/lib/i18n";
import type { CodeOption, Options } from "@/lib/types";
import { useApp } from "./AppState";

const FIRST = 8;

export const codeKey = (o: { code_system: string; code: string }) => `${o.code_system}:${o.code}`;
export const serviceKey = (slug: string) => `svc:${slug}`;

// what to call each selected item (shown on chips and price lines)
export function optionNames(data: Options | null, lang: "en" | "es"): Record<string, string> {
  const out: Record<string, string> = {};
  if (!data) return out;
  for (const s of data.services) out[serviceKey(s.slug)] = lang === "es" ? SERVICE_ES[s.slug] ?? s.name : s.name;
  for (const g of data.groups) for (const o of g.options) out[codeKey(o)] = o.service && lang === "es" ? SERVICE_ES[o.service] ?? o.name : o.name;
  return out;
}

export function OptionPicker({
  data,
  selected,
  onChange,
  priceHref,
}: {
  data: Options;
  selected: string[];
  onChange: (next: string[]) => void;
  // a link to one option's prices on its own, or null to hide it
  priceHref?: (key: string) => string | null;
}) {
  const { t, lang } = useApp();
  const [filter, setFilter] = useState("");
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const stayKeys = new Set((data.groups.find((g) => g.group === "stay")?.options ?? []).map(codeKey));

  function toggle(key: string) {
    if (selected.includes(key)) {
      onChange(selected.filter((k) => k !== key));
      return;
    }
    // one hospital stay at a time: choosing a stay replaces another stay
    const keep = stayKeys.has(key) ? selected.filter((k) => !stayKeys.has(k)) : selected;
    onChange([...keep, key]);
  }

  const needle = filter.trim().toLowerCase();
  const shown = (o: CodeOption) =>
    !needle ||
    o.name.toLowerCase().includes(needle) ||
    (o.wording ?? "").toLowerCase().includes(needle) ||
    `${o.code_system} ${o.code}`.toLowerCase().includes(needle);
  const groupLabel = (g: string) => (t as unknown as Record<string, string>)[`optionGroup_${g}`] ?? g;
  const label = (slug: string, name: string) => (lang === "es" ? SERVICE_ES[slug] ?? name : name);

  function Row(props: { k: string; name: string; wording?: string | null; code?: string; places?: number; radio?: boolean }) {
    const on = selected.includes(props.k);
    const href = priceHref?.(props.k) ?? null;
    return (
      <li className={on ? "pick on" : "pick"}>
        <label className="pick-main">
          <input type={props.radio ? "radio" : "checkbox"} checked={on} onChange={() => toggle(props.k)} onClick={() => props.radio && on && toggle(props.k)} />
          <span className="pick-text">
            <span className="option-name">{props.name}</span>
            {props.wording && (
              <span className="option-wording">
                {t.theirWording}: “{props.wording}”
              </span>
            )}
            {(props.code || props.places !== undefined) && (
              <span className="option-meta">
                {props.code && <span className="option-code">{props.code}</span>}
                {props.places !== undefined && (
                  <span>{props.places === 1 ? t.optionsPlaces1 : fill(t.optionsPlaces, { n: String(props.places) })}</span>
                )}
              </span>
            )}
          </span>
        </label>
        {href && (
          <Link className="pick-alone" href={href}>
            {t.pickAlone}
          </Link>
        )}
      </li>
    );
  }

  return (
    <div className="option-picker">
      <label className="field options-filter">
        <span>{t.optionsFilter}</span>
        <input value={filter} placeholder={t.optionsFilterPh} onChange={(e) => setFilter(e.target.value)} />
      </label>
      <p className="fine options-how">{t.optionsHowTo}</p>
      {data.services.length > 0 && !needle && (
        <section className="options-group">
          <h2>
            {t.optionsServices} <span className="options-count">{data.services.length}</span>
          </h2>
          <ul className="options-list">
            {data.services.map((s) => (
              <Row key={s.slug} k={serviceKey(s.slug)} name={label(s.slug, s.name)} wording={null} />
            ))}
          </ul>
        </section>
      )}
      {data.groups.map((g) => {
        const items = g.options.filter(shown);
        if (!items.length) return null;
        const all = openGroups[g.group] || Boolean(needle);
        // selected options always stay visible
        const list = all ? items : items.filter((o, i) => i < FIRST || selected.includes(codeKey(o)));
        return (
          <section key={g.group} className="options-group">
            <h2>
              {groupLabel(g.group)} <span className="options-count">{items.length}</span>
            </h2>
            {g.group === "stay" && <p className="fine pick-hint">{t.pickOneStay}</p>}
            <ul className="options-list">
              {list.map((o) => (
                <Row
                  key={codeKey(o)}
                  k={codeKey(o)}
                  name={o.service ? label(o.service, o.name) : o.name}
                  wording={o.wording}
                  code={`${o.code_system} ${o.code}`}
                  places={o.places}
                  radio={g.group === "stay"}
                />
              ))}
            </ul>
            {items.length > FIRST && !needle && (
              <button type="button" className="btn ghost sm" onClick={() => setOpenGroups((s) => ({ ...s, [g.group]: !s[g.group] }))}>
                {all ? t.optionsShowFewer : fill(t.optionsShowAll, { n: String(items.length) })}
              </button>
            )}
          </section>
        );
      })}
    </div>
  );
}

"use client";

// Choose insurance up front (Cooper, 2026-11-12).
// - Only insurers that places near the person published prices for.
// - Grouped by insurance company, each with its plans and a "Not sure which
//   plan?" choice that shows the range across that company's work and
//   individual plans (typing "Blue Cross" listed ~15 names and Cooper couldn't
//   tell which was his).
// - Names exactly as hospitals wrote them come last (D-046).
// - "How do I know which plan I have?" explains how to read an insurance card.

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { fitsType, matchCard, readCard, type CardHint } from "@/lib/cardRead";
import type { Plan } from "@/lib/types";
import { useApp } from "./AppState";
import { ExtText } from "./ExtText";

export type Insurance =
  | { plan: string; label: string }
  | { payer: string; label: string }
  | { insurer: string; label: string };

type Near = { lat: string; lng: string } | null;

const LEFT_OUT_OF_RANGE = ["medicare_advantage", "medicaid_managed_care"];

export function InsurancePicker({
  id,
  value,
  onChange,
  near = null,
}: {
  id: string;
  value: Insurance | null;
  onChange: (v: Insurance | null) => void;
  near?: Near;
}) {
  const { t } = useApp();
  const [q, setQ] = useState(value?.label ?? "");
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [written, setWritten] = useState<{ name: string; facilities: number }[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // a photo of the card, read on this device only (Cooper, 2026-11-12)
  const [card, setCard] = useState<CardHint | null>(null);
  const [reading, setReading] = useState(false);
  const [cardError, setCardError] = useState<string | null>(null);
  const nearKey = near ? `${near.lat},${near.lng}` : "";

  useEffect(() => {
    if (value) setQ(value.label);
  }, [value]);

  useEffect(() => {
    let live = true;
    api
      .plans(near)
      .then((p) => live && setPlans(p))
      .catch(() => live && setPlans([]));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nearKey]);

  useEffect(() => {
    if (value && q === value.label) return;
    if (q.trim().length < 2) {
      setWritten([]);
      return;
    }
    const tid = setTimeout(
      () => api.payerSuggest(q, near).then(setWritten).catch(() => setWritten([])),
      150,
    );
    return () => clearTimeout(tid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, value, nearKey]);

  const needle = q.trim().toLowerCase();
  // insurance companies whose name or plan names match, each with its plans
  const companies = useMemo(() => {
    if (needle.length < 2 || !plans) return [];
    const groups = new Map<string, { payer: string; payerId: string; plans: Plan[] }>();
    for (const p of plans) {
      const key = p.payer_id || p.payer;
      const g = groups.get(key) ?? { payer: p.payer, payerId: p.payer_id ?? "", plans: [] };
      g.plans.push(p);
      groups.set(key, g);
    }
    const type = card?.planType ?? null;
    return Array.from(groups.values())
      .filter((g) => g.payer.toLowerCase().includes(needle) || g.plans.some((p) => p.plan.toLowerCase().includes(needle)))
      .map((g) => ({
        ...g,
        // plans that fit the type on the card come first
        plans: type ? [...g.plans].sort((a, b) => Number(fitsType(b, type)) - Number(fitsType(a, type))) : g.plans,
      }))
      .slice(0, 5);
  }, [plans, needle, card]);

  async function onPhoto(file: File | undefined) {
    if (!file) return;
    setReading(true);
    setCardError(null);
    try {
      const [text, list] = await Promise.all([readCard(file), plans ?? api.plans(near).catch(() => [])]);
      if (!plans) setPlans(list);
      const hint = matchCard(text, list);
      setCard(hint);
      if (hint.payer) {
        setQ(hint.payer.replace(/\s*\(.*?\)\s*/g, " ").trim());
        if (value) onChange(null);
        setOpen(true);
      } else {
        setCardError(t.cardNoMatch);
      }
    } catch {
      setCardError(t.cardFailed);
    } finally {
      setReading(false);
    }
  }
  const writtenHits = written
    .filter((w) => !companies.some((c) => c.payer.toLowerCase() === w.name.toLowerCase()))
    .slice(0, companies.length >= 3 ? 3 : 6);

  function pick(v: Insurance) {
    setQ(v.label);
    setOpen(false);
    setActive(-1);
    onChange(v);
  }

  // every choice in list order, so the arrow keys and Enter work too
  // (keyboard and screen-reader users, 2026-11-12)
  const choices: { key: string; v: Insurance }[] = [];
  for (const c of companies) {
    const rangePlans = c.plans.filter((p) => !LEFT_OUT_OF_RANGE.includes(p.segment));
    if (c.payerId && rangePlans.length > 1) {
      choices.push({ key: `u:${c.payerId}`, v: { insurer: c.payerId, label: t.insUnsureLabel.replace("{payer}", c.payer) } });
    }
    for (const p of c.plans) choices.push({ key: `p:${p.plan_id}`, v: { plan: p.plan_id, label: `${p.payer} · ${p.plan}` } });
  }
  for (const w of writtenHits) choices.push({ key: `w:${w.name}`, v: { payer: w.name, label: w.name } });
  const optId = (key: string) => `${id}-opt-${choices.findIndex((c) => c.key === key)}`;
  const isActive = (key: string) => active >= 0 && choices[active]?.key === key;

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!choices.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => (a + 1) % choices.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? choices.length - 1 : a - 1));
    } else if (e.key === "Enter" && open && active >= 0 && choices[active]) {
      e.preventDefault();
      pick(choices[active]!.v);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActive(-1);
    }
  }

  const nothingNear = near !== null && plans !== null && plans.length === 0 && needle.length < 2;
  const noMatch = needle.length >= 2 && plans !== null && companies.length === 0 && writtenHits.length === 0 && !value;

  return (
    <div className="insurance-picker">
      <input
        id={id}
        autoComplete="off"
        placeholder={t.insurerPh}
        value={q}
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        aria-activedescendant={open && active >= 0 && choices[active] ? `${id}-opt-${active}` : undefined}
        onKeyDown={onKey}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setActive(-1);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (companies.length > 0 || writtenHits.length > 0) && (
        <ul className="suggest ins-list" role="listbox" id={`${id}-list`}>
          {companies.map((c) => {
            const rangePlans = c.plans.filter((p) => !LEFT_OUT_OF_RANGE.includes(p.segment));
            return (
              <li key={c.payerId || c.payer} className="ins-company" role="presentation">
                <span className="ins-company-name">{c.payer}</span>
                <ul role="group" aria-label={c.payer}>
                  {c.payerId && rangePlans.length > 1 && (
                    <li
                      id={optId(`u:${c.payerId}`)}
                      role="option"
                      aria-selected={isActive(`u:${c.payerId}`)}
                      className={isActive(`u:${c.payerId}`) ? "ins-unsure on" : "ins-unsure"}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        pick({ insurer: c.payerId, label: t.insUnsureLabel.replace("{payer}", c.payer) });
                      }}
                    >
                      {t.insNotSure.replace("{payer}", c.payer)}
                    </li>
                  )}
                  {c.plans.map((p) => (
                    <li
                      key={p.plan_id}
                      id={optId(`p:${p.plan_id}`)}
                      role="option"
                      aria-selected={isActive(`p:${p.plan_id}`)}
                      className={isActive(`p:${p.plan_id}`) ? "on" : undefined}
                      onMouseDown={(e) => {
                        e.preventDefault();
                        pick({ plan: p.plan_id, label: `${p.payer} · ${p.plan}` });
                      }}
                    >
                      {p.plan}
                    </li>
                  ))}
                </ul>
              </li>
            );
          })}
          {writtenHits.length > 0 && (
            <li className="ins-company" role="presentation">
              <span className="ins-company-name">{t.insOtherNames}</span>
              <ul role="group" aria-label={t.insOtherNames}>
                {writtenHits.map((w) => (
                  <li
                    key={w.name}
                    id={optId(`w:${w.name}`)}
                    role="option"
                    aria-selected={isActive(`w:${w.name}`)}
                    className={isActive(`w:${w.name}`) ? "on" : undefined}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      pick({ payer: w.name, label: w.name });
                    }}
                  >
                    <span>{w.name}</span>
                    <span className="suggest-why">{t.payerWrittenPlaces.replace("{n}", String(w.facilities))}</span>
                  </li>
                ))}
              </ul>
            </li>
          )}
        </ul>
      )}
      <label className="card-photo">
        <input
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => {
            void onPhoto(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <span className="btn ghost sm">{reading ? t.cardReading : t.cardButton}</span>
        <span className="fine">{t.cardPrivate}</span>
      </label>
      {card && card.found.length > 0 && (
        <p className="ins-note card-read">{t.cardFound.replace("{what}", card.found.join(" · "))}</p>
      )}
      {cardError && <p className="ins-note">{cardError}</p>}
      {nothingNear && <p className="ins-note">{t.insNoneNear}</p>}
      {noMatch && <p className="ins-note">{t.insNoMatch}</p>}
      <details className="plan-help">
        <summary>{t.planHelpTitle}</summary>
        <ol>
          {[t.planHelp1, t.planHelp2, t.planHelp3, t.planHelp4, t.planHelp5, t.planHelp6, t.planHelp7].map((line) => (
            <li key={line}>
              <ExtText text={line} />
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}

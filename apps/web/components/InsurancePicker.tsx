"use client";

// Choose insurance up front (Cooper, 2026-11-12): the plans we have matched
// by card name first, then insurer names exactly as hospitals wrote them.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Plan } from "@/lib/types";
import { useApp } from "./AppState";

export type Insurance = { plan: string; label: string } | { payer: string; label: string };

export function InsurancePicker({ id, value, onChange }: { id: string; value: Insurance | null; onChange: (v: Insurance | null) => void }) {
  const { t } = useApp();
  const [q, setQ] = useState(value?.label ?? "");
  const [plans, setPlans] = useState<Plan[]>([]);
  const [written, setWritten] = useState<{ name: string; facilities: number }[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.plans().then(setPlans).catch(() => setPlans([]));
  }, []);
  useEffect(() => {
    if (value && q === value.label) return;
    if (q.trim().length < 2) {
      setWritten([]);
      return;
    }
    const tid = setTimeout(() => api.payerSuggest(q).then(setWritten).catch(() => setWritten([])), 150);
    return () => clearTimeout(tid);
  }, [q, value]);

  const needle = q.trim().toLowerCase();
  const planHits =
    needle.length < 2 ? [] : plans.filter((p) => `${p.payer} ${p.plan}`.toLowerCase().includes(needle)).slice(0, 8);
  const writtenHits = written.filter((w) => !planHits.some((p) => p.payer.toLowerCase() === w.name.toLowerCase())).slice(0, 6);

  return (
    <div className="insurance-picker">
      <input
        id={id}
        autoComplete="off"
        placeholder={t.insurerPh}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && (planHits.length > 0 || writtenHits.length > 0) && (
        <ul className="suggest" role="listbox">
          {planHits.map((p) => (
            <li
              key={p.plan_id}
              role="option"
              aria-selected={false}
              onMouseDown={(e) => {
                e.preventDefault();
                const label = `${p.payer} · ${p.plan}`;
                setQ(label);
                setOpen(false);
                onChange({ plan: p.plan_id, label });
              }}
            >
              <span>
                {p.payer} · {p.plan}
              </span>
            </li>
          ))}
          {writtenHits.map((w) => (
            <li
              key={w.name}
              role="option"
              aria-selected={false}
              onMouseDown={(e) => {
                e.preventDefault();
                setQ(w.name);
                setOpen(false);
                onChange({ payer: w.name, label: w.name });
              }}
            >
              <span>{w.name}</span>
              <span className="suggest-why">{t.payerWrittenPlaces.replace("{n}", String(w.facilities))}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

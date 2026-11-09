"use client";

// "Don't see your plan?": find rates under an insurer's name exactly as the
// hospitals wrote it, before that name is matched to a card name (D-046).

import { useEffect, useState } from "react";
import { useApp } from "./AppState";
import { api } from "@/lib/api";

export function PayerAsWritten({ current, onPick }: { current: string | null; onPick: (name: string | null) => void }) {
  const { t } = useApp();
  const [q, setQ] = useState("");
  const [options, setOptions] = useState<{ name: string; facilities: number }[]>([]);
  useEffect(() => {
    if (q.trim().length < 2) {
      setOptions([]);
      return;
    }
    const id = setTimeout(() => api.payerSuggest(q).then(setOptions).catch(() => setOptions([])), 150);
    return () => clearTimeout(id);
  }, [q]);
  if (current) {
    return (
      <div className="notice payer-written">
        <p>{t.payerWrittenNote.replace("{name}", current)}</p>
        <button type="button" className="btn ghost sm" onClick={() => onPick(null)}>
          {t.change}
        </button>
      </div>
    );
  }
  return (
    <details className="payer-written-box">
      <summary>{t.payerWrittenAsk}</summary>
      <div className="field">
        <label htmlFor="payer-q">{t.payerWrittenLabel}</label>
        <input id="payer-q" autoComplete="off" placeholder={t.payerWrittenPh} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {options.length > 0 && (
        <ul className="pick-list">
          {options.map((o) => (
            <li key={o.name}>
              <button type="button" onClick={() => onPick(o.name)}>
                <strong>{o.name}</strong>
                <span>{t.payerWrittenPlaces.replace("{n}", String(o.facilities))}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

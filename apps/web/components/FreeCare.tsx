"use client";

import Link from "next/link";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { cleanIncome } from "@/lib/money";
import type { AssistanceMessage } from "@/lib/types";
import { useApp } from "./AppState";
import { Heart, Lock } from "./Icons";

/** Household size + income fields, shared by the home panel and the help page. */
export function CareFields({
  size,
  setSize,
  income,
  setIncome,
}: {
  size: number;
  setSize: (n: number) => void;
  income: string;
  setIncome: (s: string) => void;
}) {
  const { t } = useApp();
  const id = useId();
  return (
    <div className="care-fields">
      <div className="field">
        <label htmlFor={`${id}-size`}>{t.careHousehold}</label>
        <div className="stepper">
          <button type="button" aria-label="−" onClick={() => setSize(Math.max(1, size - 1))}>
            −
          </button>
          <input
            id={`${id}-size`}
            inputMode="numeric"
            value={size}
            onChange={(e) => {
              const n = Number(e.target.value.replace(/\D/g, ""));
              if (n >= 1 && n <= 20) setSize(n);
            }}
          />
          <button type="button" aria-label="+" onClick={() => setSize(Math.min(20, size + 1))}>
            +
          </button>
        </div>
      </div>
      <div className="field">
        <label htmlFor={`${id}-income`}>{t.careIncome}</label>
        <input
          id={`${id}-income`}
          inputMode="decimal"
          autoComplete="off"
          placeholder={t.careIncomePh}
          value={income}
          onChange={(e) => setIncome(e.target.value)}
        />
      </div>
    </div>
  );
}

export function FreeCarePanel() {
  const { t, place, setPlace, setCare } = useApp();
  const router = useRouter();
  const id = useId();
  const [msg, setMsg] = useState<AssistanceMessage | null>(null);
  const [size, setSize] = useState(1);
  const [income, setIncome] = useState("");
  // the ZIP is asked here too, so the answer comes in one step (Cooper, 2026-11-23)
  const [zip, setZip] = useState(place?.zip ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (place?.zip && !zip) setZip(place.zip);
  }, [place?.zip]);

  useEffect(() => {
    api
      .message(place?.state ?? null)
      .then(setMsg)
      .catch(() => setMsg(null));
  }, [place?.state]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const clean = cleanIncome(income);
    if (!clean) {
      setError(t.careBadIncome);
      return;
    }
    if (!/^\d{5}$/.test(zip)) {
      setError(t.badZip);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const p = place?.zip === zip ? place : await api.zip(zip);
      setPlace(p);
      setCare({ householdSize: size, income: clean });
      router.push("/help-paying");
    } catch {
      setError(t.zipNotFound);
      setBusy(false);
    }
  }

  return (
    <section className="care-panel" aria-labelledby="care-title">
      <div className="care-head">
        <span className="care-icon">
          <Heart size={22} />
        </span>
        <h2 id="care-title">{t.careTitle}</h2>
      </div>
      <p className="care-msg">{msg?.message ?? " "}</p>
      <p className="care-sub">{t.careEvenInsured}</p>
      <p className="care-free">
        <strong>{t.bannerNotLoan}</strong>{" "}
        <Link href="/help-paying#what">{t.bannerWhat}</Link>
      </p>
      <form onSubmit={submit} noValidate>
        <CareFields size={size} setSize={setSize} income={income} setIncome={setIncome} />
        <div className="field care-zip">
          <label htmlFor={`${id}-zip`}>{t.helpZip}</label>
          <input
            id={`${id}-zip`}
            inputMode="numeric"
            autoComplete="postal-code"
            maxLength={5}
            placeholder={t.wherePlaceholder}
            value={zip}
            onChange={(e) => setZip(e.target.value.replace(/\D/g, ""))}
          />
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn care" type="submit" disabled={busy}>
          {busy ? "…" : t.careAsk}
        </button>
        <p className="fine">
          <Lock size={14} /> {t.carePrivate}
        </p>
      </form>
    </section>
  );
}

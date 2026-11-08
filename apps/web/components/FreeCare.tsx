"use client";

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
  const { t, place, setCare } = useApp();
  const router = useRouter();
  const [msg, setMsg] = useState<AssistanceMessage | null>(null);
  const [size, setSize] = useState(1);
  const [income, setIncome] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .message(place?.state ?? "NV")
      .then(setMsg)
      .catch(() => setMsg(null));
  }, [place?.state]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const clean = cleanIncome(income);
    if (!clean) {
      setError(t.careBadIncome);
      return;
    }
    setCare({ householdSize: size, income: clean });
    router.push("/help-paying");
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
      <form onSubmit={submit} noValidate>
        <CareFields size={size} setSize={setSize} income={income} setIncome={setIncome} />
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <button className="btn care" type="submit">
          {t.careAsk}
        </button>
        <p className="fine">
          <Lock size={14} /> {t.carePrivate}
        </p>
      </form>
    </section>
  );
}

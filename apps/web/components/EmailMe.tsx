"use client";

// "Email this to me" on a result card (Cooper, 2026-11-12): the prices, the
// codes, a link to the hospital's own file and how to look the code up in it.

import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { Mode } from "@/lib/types";
import { useApp } from "./AppState";

export function EmailMe(props: {
  facilityId: string;
  service?: string | null;
  codeSystem?: string | null;
  code?: string | null;
  mode: Mode;
  planId?: string | null;
  payerId?: string | null;
  payer?: string | null;
  planLabel?: string | null;
}) {
  const { t, lang } = useApp();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setState("sending");
    try {
      await api.emailPrices({ ...props, email: email.trim(), lang });
      setState("sent");
    } catch (err) {
      setError((err as Error).message);
      setState("idle");
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn ghost sm" onClick={() => setOpen(true)}>
        {t.emailMe}
      </button>
    );
  }
  return (
    <div className="email-me">
      {state === "sent" ? (
        <p className="email-sent">{t.emailSent}</p>
      ) : (
        <form onSubmit={send}>
          <label htmlFor={`em-${props.facilityId}`}>{t.emailLabel}</label>
          <div className="email-row">
            <input
              id={`em-${props.facilityId}`}
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
            <button className="btn primary sm" type="submit" disabled={state === "sending"}>
              {state === "sending" ? t.emailSending : t.emailSend}
            </button>
          </div>
          <p className="fine">{t.emailWhat}</p>
          {error && <p className="form-error">{error}</p>}
        </form>
      )}
    </div>
  );
}

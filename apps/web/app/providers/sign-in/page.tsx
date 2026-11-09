"use client";

import Link from "next/link";
import { useState } from "react";
import { useApp } from "@/components/AppState";
import { Lock, Logo } from "@/components/Icons";
import { portalText } from "@/lib/i18n_portal";
import { portal } from "@/lib/portal";

// Provider sign-in (D-050): a one-time link by email, then an authenticator
// app code. The page answers the same whether or not the email has an account.
export default function ProviderSignIn() {
  const { t, lang } = useApp();
  const p = portalText(lang);
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [err, setErr] = useState("");
  const [dev, setDev] = useState<string | null>(null);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("sending");
    setErr("");
    try {
      const r = await portal.signIn(email);
      setDev(r.dev_link);
      setState("sent");
    } catch (ex) {
      setErr((ex as Error).message);
      setState("idle");
    }
  };

  return (
    <div className="wrap page signin-wrap">
      <div className="card signin">
        <Logo size={40} />
        <h1>{state === "sent" ? p.sentTitle : t.signInTitle}</h1>
        {state === "sent" ? (
          <>
            <p className="signin-sub">{p.sentBody}</p>
            {dev && (
              <p className="notice">
                {p.devLink}: <a href={dev}>{dev}</a>
              </p>
            )}
          </>
        ) : (
          <>
            <p className="signin-sub">{t.signInSub}</p>
            <form onSubmit={send}>
              <div className="field">
                <label htmlFor="email">{t.signInEmail}</label>
                <input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              {err && <p className="form-error">{err}</p>}
              <button className="btn primary" type="submit" disabled={state === "sending"}>
                {t.signInSend}
              </button>
            </form>
          </>
        )}
        <p className="fine">
          <Lock size={14} /> {t.signInSecurity}
        </p>
        <p className="signin-new" id="claim">
          {t.signInNew} <Link href="/providers">{t.signInClaim}</Link>
        </p>
      </div>
    </div>
  );
}

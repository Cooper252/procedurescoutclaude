"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { Lock, Logo } from "@/components/Icons";

// Provider accounts are not built yet (PRV-01, Phase 9). This screen shows
// where sign-in will be and says plainly that it is not open; the form does
// nothing and sends nothing.
export default function ProviderSignIn() {
  const { t } = useApp();
  return (
    <div className="wrap page signin-wrap">
      <div className="card signin">
        <Logo size={40} />
        <h1>{t.signInTitle}</h1>
        <p className="signin-sub">{t.signInSub}</p>
        <p className="notice">{t.signInNotYet}</p>
        <form onSubmit={(e) => e.preventDefault()} aria-disabled="true">
          <div className="field">
            <label htmlFor="email">{t.signInEmail}</label>
            <input id="email" type="email" autoComplete="email" disabled />
          </div>
          <button className="btn primary" type="submit" disabled>
            {t.signInSend}
          </button>
        </form>
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

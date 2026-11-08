"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { FileCheck, Search, Shield, Receipt } from "@/components/Icons";

export default function Providers() {
  const { t } = useApp();
  const steps = [
    { icon: <Search size={22} />, title: t.provStep1t, body: t.provStep1 },
    { icon: <Shield size={22} />, title: t.provStep2t, body: t.provStep2 },
    { icon: <Receipt size={22} />, title: t.provStep3t, body: t.provStep3 },
    { icon: <FileCheck size={22} />, title: t.provStep4t, body: t.provStep4 },
  ];
  return (
    <>
      <section className="prov-hero">
        <div className="wrap">
          <p className="eyebrow">{t.navProviders}</p>
          <h1 className="page-title">{t.provTitle}</h1>
          <p className="lead">{t.provSub}</p>
          <div className="prov-ctas">
            <Link className="btn primary" href="/providers/sign-in#claim">
              {t.provClaimBtn}
            </Link>
            <Link className="btn ghost" href="/providers/sign-in">
              {t.provSignInBtn}
            </Link>
          </div>
        </div>
      </section>
      <div className="wrap page">
        <h2 className="section-title">{t.provStepsTitle}</h2>
        <ol className="prov-steps">
          {steps.map((s, i) => (
            <li key={s.title}>
              <span className="how-icon">{s.icon}</span>
              <h3>
                {i + 1}. {s.title}
              </h3>
              <p>{s.body}</p>
            </li>
          ))}
        </ol>
        <div className="prov-grid">
          <section className="card prov-box">
            <h2>{t.provRulesTitle}</h2>
            <ul className="checks">
              <li>{t.provRule1}</li>
              <li>{t.provRule2}</li>
              <li>{t.provRule3}</li>
              <li>{t.provRule4}</li>
            </ul>
          </section>
          <section className="card prov-box">
            <h2>{t.provPriceTitle}</h2>
            <p>{t.provPrice}</p>
          </section>
        </div>
      </div>
    </>
  );
}

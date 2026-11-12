"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { ExtText } from "@/components/ExtText";
import { Receipt } from "@/components/Icons";

export default function BillHelp() {
  const { t } = useApp();
  const steps: [string, string][] = [
    [t.billStep1t, t.billStep1],
    [t.billStep2t, t.billStep2],
    [t.billStep3t, t.billStep3],
    [t.billStep4t, t.billStep4],
    [t.billStep5t, t.billStep5],
  ];
  return (
    <div className="wrap page narrow">
      <p className="eyebrow">
        <Receipt size={16} /> {t.navBill}
      </p>
      <h1 className="page-title">{t.billPageTitle}</h1>
      <p className="lead">{t.billPageSub}</p>
      <ol className="steps">
        {steps.map(([title, body], i) => (
          <li key={i} className="step">
            <span className="step-n" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <h2>{title}</h2>
              <p>
                <ExtText text={body} />
              </p>
              {i === 0 && (
                <Link className="btn ghost sm" href="/">
                  {t.billCheckPrices}
                </Link>
              )}
              {i === 2 && (
                <Link className="btn care sm" href="/help-paying">
                  {t.billCheckHelp}
                </Link>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

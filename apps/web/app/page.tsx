"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { FreeCarePanel } from "@/components/FreeCare";
import { Arrow, FileCheck, Lock, Receipt, Shield } from "@/components/Icons";
import { SearchForm } from "@/components/SearchForm";
import { SERVICE_ES } from "@/lib/i18n";

const POPULAR: { slug: string; name: string }[] = [
  { slug: "mri-brain-without-contrast", name: "MRI of the brain" },
  { slug: "colonoscopy-diagnostic", name: "Colonoscopy" },
  { slug: "teeth-cleaning-adult", name: "Teeth cleaning" },
  { slug: "complete-blood-count", name: "Blood work (CBC)" },
  { slug: "botox-per-unit", name: "Botox" },
  { slug: "cataract-surgery", name: "Cataract surgery" },
];

export default function Home() {
  const { t, lang, place } = useApp();
  const short = (s: { slug: string; name: string }) =>
    lang === "es" ? (SERVICE_ES[s.slug] ?? s.name).replace(/ \(.*\)$/, "") : s.name;
  return (
    <>
      <section className="hero">
        <div className="wrap hero-grid">
          <div className="hero-main">
            <h1>{t.heroTitle}</h1>
            <p className="lead">{t.heroSub}</p>
            <div className="card search-card">
              <SearchForm />
            </div>
            <div className="popular">
              <h2 className="eyebrow">{t.popular}</h2>
              <ul className="chips">
                {POPULAR.map((p) => (
                  <li key={p.slug}>
                    <Link
                      className="chip"
                      href={`/search?service=${p.slug}${place ? `&zip=${place.zip}` : ""}`}
                    >
                      {short(p)}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="hero-side">
            <FreeCarePanel />
          </div>
        </div>
      </section>

      <section className="wrap band">
        <Link href="/bill" className="bill-card">
          <span className="bill-icon">
            <Receipt size={26} />
          </span>
          <span className="bill-text">
            <strong>{t.billTitle}</strong>
            <span>{t.billSub}</span>
          </span>
          <span className="bill-cta">
            {t.billCta} <Arrow size={18} />
          </span>
        </Link>
      </section>

      <section className="wrap band two">
        <Link href="/bundles" className="mini-card">
          <strong>{t.bunTitle}</strong>
          <span>{t.bunSub}</span>
        </Link>
        <Link href="/learn" className="mini-card">
          <strong>{t.learnTitle}</strong>
          <span>{t.learnSub}</span>
        </Link>
      </section>

      <section className="wrap trust" aria-label="Why trust these prices">
        <div className="trust-item">
          <FileCheck size={24} />
          <p>{t.trust1}</p>
        </div>
        <div className="trust-item">
          <Shield size={24} />
          <p>{t.trust2}</p>
        </div>
        <div className="trust-item">
          <Lock size={24} />
          <p>{t.trust3}</p>
        </div>
      </section>
    </>
  );
}

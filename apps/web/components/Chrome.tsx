"use client";

// Header (free-care banner, emergency line, navigation, language) and footer:
// on every page (docs/SITE_DESIGN.md §1).

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { DEMO } from "@/lib/api";
import { useApp } from "./AppState";
import { Alert, Globe, Heart, Logo } from "./Icons";

export function Header() {
  const { t, lang, setLang } = useApp();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const nav = [
    { href: "/", label: t.navSearch },
    { href: "/help-paying", label: t.navHelp },
    { href: "/bill", label: t.navBill },
    { href: "/how-it-works", label: t.navHow },
    { href: "/providers", label: t.navProviders },
  ];
  return (
    <>
      <a className="skip" href="#main">
        {t.skip}
      </a>
      {DEMO && (
        <div className="preview" role="note">
          {t.preview}
        </div>
      )}
      <div className="utility">
        <div className="wrap utility-in">
          <span className="utility-er">
            <Alert size={15} />
            <span className="hide-sm">{t.emergency}</span>
            <span className="show-sm">{t.emergencyShort}</span>
          </span>
          <button
            type="button"
            className="lang"
            onClick={() => setLang(lang === "en" ? "es" : "en")}
            lang={lang === "en" ? "es" : "en"}
          >
            <Globe size={15} /> {t.language}
          </button>
        </div>
      </div>
      <header className="header">
        <div className="wrap header-in">
          <Link href="/" className="brand" aria-label="ProcedureScout home">
            <Logo />
            <span className="brand-text">
              <span className="brand-name">ProcedureScout</span>
              <span className="brand-tag hide-sm">{t.brandTag}</span>
            </span>
          </Link>
          <nav className="nav hide-md" aria-label="Main">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} className={path === n.href ? "nav-link on" : "nav-link"}>
                {n.label}
              </Link>
            ))}
          </nav>
          <Link href="/providers/sign-in" className="btn ghost sm signin-link hide-md">
            {t.providerSignIn}
          </Link>
          <button
            type="button"
            className="menu-btn show-md"
            aria-expanded={open}
            aria-controls="mobile-nav"
            onClick={() => setOpen(!open)}
          >
            <span className="menu-bars" aria-hidden="true" />
            <span className="sr">Menu</span>
          </button>
        </div>
        {open && (
          <nav id="mobile-nav" className="mobile-nav show-md" aria-label="Main">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} onClick={() => setOpen(false)} className="mobile-link">
                {n.label}
              </Link>
            ))}
            <Link href="/learn" onClick={() => setOpen(false)} className="mobile-link">
              {t.navLearn}
            </Link>
            <Link href="/providers/sign-in" onClick={() => setOpen(false)} className="mobile-link">
              {t.providerSignIn}
            </Link>
          </nav>
        )}
      </header>
      {path !== "/help-paying" && (
        <div className="care-banner">
          <span className="wrap care-banner-in">
            <Heart size={18} />
            <span>
              <Link href="/help-paying" className="care-banner-main">
                <strong>{t.bannerLead}</strong> <span className="care-banner-free">{t.bannerNotLoan}</span>{" "}
                <span className="care-banner-cta">{t.bannerCta} →</span>
              </Link>{" "}
              <Link href="/help-paying#what" className="care-banner-what">
                {t.bannerWhat}
              </Link>
            </span>
          </span>
        </div>
      )}
    </>
  );
}

export function Footer() {
  const { t } = useApp();
  return (
    <footer className="footer">
      <div className="wrap footer-in">
        <div className="footer-brand">
          <Logo size={26} />
          <span>ProcedureScout</span>
        </div>
        <p>{t.footerData}</p>
        <p className="footer-disclaimer">{t.footerDisclaimer}</p>
        <p>
          <strong>{t.emergency}</strong> {t.footerNotAdvice}
        </p>
        <nav className="footer-nav" aria-label="Footer">
          <Link href="/how-it-works">{t.navHow}</Link>
          <Link href="/help-paying">{t.navHelp}</Link>
          <Link href="/bill">{t.navBill}</Link>
          <Link href="/learn">{t.navLearn}</Link>
          <Link href="/bundles">{t.bunTitle}</Link>
          <Link href="/prices">{t.areaBrowse}</Link>
          <Link href="/providers">{t.navProviders}</Link>
          <Link href="/providers/sign-in">{t.providerSignIn}</Link>
          <Link href="/disclaimer">{t.navDisclaimer}</Link>
          <Link href="/terms">{t.navTerms}</Link>
          <Link href="/privacy">{t.navPrivacy}</Link>
        </nav>
        <p className="footer-copy">© {new Date().getFullYear()} ProcedureScout</p>
      </div>
    </footer>
  );
}

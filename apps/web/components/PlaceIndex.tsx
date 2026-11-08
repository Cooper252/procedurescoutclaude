"use client";

import Link from "next/link";
import { useApp } from "./AppState";
import { fill, SERVICE_ES, type Dict } from "@/lib/i18n";
import type { AreaLink } from "./AreaView";

export interface IndexSection {
  heading: keyof Dict;
  vars?: Record<string, string>;
  links: AreaLink[];
}

export function PlaceIndex({
  title,
  vars,
  sections,
  children,
}: {
  title: keyof Dict;
  vars?: Record<string, string>;
  sections: IndexSection[];
  children?: React.ReactNode;
}) {
  const { t, lang } = useApp();
  return (
    <div className="wrap page narrow">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link href="/prices">{t.areaBrowse}</Link>
      </nav>
      <h1 className="page-title">{fill(t[title], vars ?? {})}</h1>
      {children}
      {sections.map((s) => (
        <section key={String(s.heading)} className="area-links">
          <h2>{fill(t[s.heading], s.vars ?? {})}</h2>
          <ul className="chips">
            {s.links.map((l) => (
              <li key={l.href}>
                <Link className="chip" href={l.href}>
                  {lang === "es" && l.slug ? (SERVICE_ES[l.slug] ?? l.label).replace(/ \(.*\)$/, "") : l.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

"use client";

import { LEGAL } from "@/lib/legal";
import { useApp } from "./AppState";

export function LegalPage({ doc }: { doc: "disclaimer" | "terms" | "privacy" }) {
  const { lang } = useApp();
  const d = LEGAL[lang][doc];
  return (
    <div className="wrap page narrow legal">
      <h1 className="page-title">{d.title}</h1>
      <p className="legal-updated">{d.updated}</p>
      <p className="lead">{d.intro}</p>
      {d.sections.map((s) => (
        <section key={s.h}>
          <h2>{s.h}</h2>
          {s.p.map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </section>
      ))}
    </div>
  );
}

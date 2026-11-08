"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { GUIDES } from "@/lib/learn";

export default function Learn() {
  const { t, lang } = useApp();
  return (
    <div className="wrap page narrow">
      <h1 className="page-title">{t.learnTitle}</h1>
      <p className="lead">{t.learnSub}</p>
      <div className="guides">
        {GUIDES[lang].map((g) => (
          <details key={g.id} id={g.id} className="guide">
            <summary>{g.q}</summary>
            {g.a.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </details>
        ))}
      </div>
      <p className="fine">
        <Link href="/disclaimer">{t.navDisclaimer}</Link>
      </p>
    </div>
  );
}

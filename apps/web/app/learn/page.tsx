"use client";

import Link from "next/link";
import { useApp } from "@/components/AppState";
import { GUIDES } from "@/lib/learn";
import { PageIntro } from "@/components/PageIntro";

export default function Learn() {
  const { t, lang } = useApp();
  return (
    <>
    <PageIntro narrow title={t.learnTitle} lead={t.learnSub} />
    <div className="wrap page narrow">
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
    </>
  );
}

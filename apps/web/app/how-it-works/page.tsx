"use client";

import { useApp } from "@/components/AppState";
import { FileCheck, Search, Shield, Alert, Heart } from "@/components/Icons";
import { PageIntro } from "@/components/PageIntro";

export default function HowItWorks() {
  const { t } = useApp();
  const items = [
    { icon: <FileCheck size={24} />, title: t.how1t, body: t.how1 },
    { icon: <Alert size={24} />, title: t.how2t, body: t.how2 },
    { icon: <Shield size={24} />, title: t.how3t, body: t.how3 },
    { icon: <Search size={24} />, title: t.how4t, body: t.how4 },
    { icon: <Heart size={24} />, title: t.how5t, body: t.how5 },
  ];
  return (
    <>
    <PageIntro narrow title={t.howTitle} lead={t.howSub} />
    <div className="wrap page narrow">
      <div className="how">
        {items.map((it) => (
          <section key={it.title} className="how-item">
            <span className="how-icon">{it.icon}</span>
            <div>
              <h2>{it.title}</h2>
              <p>{it.body}</p>
            </div>
          </section>
        ))}
      </div>
      <section className="how-sources">
        <h2>{t.howSourcesTitle}</h2>
        <p className="small">{t.howSources}</p>
      </section>
    </div>
    </>
  );
}

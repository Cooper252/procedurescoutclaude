"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { useApp } from "./AppState";
import { api } from "@/lib/api";
import { SERVICE_ES } from "@/lib/i18n";
import type { Service } from "@/lib/types";

/** Go to the prices-near-a-ZIP page for one service. */
export function ZipJump() {
  const { t, lang } = useApp();
  const router = useRouter();
  const [services, setServices] = useState<Service[]>([]);
  const [zip, setZip] = useState("");
  const [svc, setSvc] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.services().then((s) => {
      setServices(s);
      setSvc((v) => v || s[0]?.slug || "");
    }).catch(() => setServices([]));
  }, []);
  function go(e: FormEvent) {
    e.preventDefault();
    if (!/^\d{5}$/.test(zip)) return setError(t.badZip);
    router.push(`/prices/zip/${zip}/${svc}`);
  }
  return (
    <form className="card zipjump" onSubmit={go} noValidate>
      <div className="field">
        <label htmlFor="zj-zip">{t.whereLabel}</label>
        <input id="zj-zip" inputMode="numeric" maxLength={5} placeholder={t.wherePlaceholder} value={zip} onChange={(e) => setZip(e.target.value.replace(/\D/g, ""))} />
      </div>
      <div className="field">
        <label htmlFor="zj-svc">{t.areaServices}</label>
        <select id="zj-svc" value={svc} onChange={(e) => setSvc(e.target.value)}>
          {services.map((s) => (
            <option key={s.slug} value={s.slug}>
              {lang === "es" ? SERVICE_ES[s.slug] ?? s.name : s.name}
            </option>
          ))}
        </select>
      </div>
      <button className="btn primary" type="submit">
        {t.searchBtn}
      </button>
      {error && <p className="form-error">{error}</p>}
    </form>
  );
}

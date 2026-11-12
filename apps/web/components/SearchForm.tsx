"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { api } from "@/lib/api";
import { fill, SERVICE_ES } from "@/lib/i18n";
import type { ProviderType, Suggestion } from "@/lib/types";
import { useApp } from "./AppState";
import { Locate, Pin, Search } from "./Icons";
import { InsurancePicker, type Insurance } from "./InsurancePicker";
import { parseTypes, TypePicker } from "./TypePicker";

const RADII = ["5", "10", "25", "50", "100"];

interface Props {
  initialService?: { slug: string; name: string } | null;
  initialZip?: string;
  initialType?: string | null;
  initialRadius?: string | null;
  initialInsurance?: Insurance | null;
  compact?: boolean;
}

export function SearchForm({
  initialService = null,
  initialZip = "",
  initialType = null,
  initialRadius = null,
  initialInsurance = null,
  compact = false,
}: Props) {
  const { t, lang, place, setPlace } = useApp();
  const router = useRouter();
  const listId = useId();
  const [text, setText] = useState(initialService?.name ?? "");
  const [picked, setPicked] = useState<{ slug: string; name: string; code_system?: string | null; code?: string | null } | null>(initialService);
  const [options, setOptions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [zip, setZip] = useState(initialZip || place?.zip || "");
  const [types, setTypes] = useState<ProviderType[]>([]);
  const [kinds, setKinds] = useState<string[]>(parseTypes(initialType));
  const [radius, setRadius] = useState<string>(RADII.includes(initialRadius ?? "") ? initialRadius! : "25");
  const [paying, setPaying] = useState<"cash" | "plan">(initialInsurance ? "plan" : "cash");
  const [insurance, setInsurance] = useState<Insurance | null>(initialInsurance);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const coords = useRef<{ lat: string; lng: string } | null>(null);

  useEffect(() => {
    api.providerTypes().then(setTypes).catch(() => setTypes([]));
  }, []);

  useEffect(() => {
    if (picked && text === picked.name) return;
    const q = text.trim();
    if (q.length < 2) {
      setOptions([]);
      return;
    }
    const id = setTimeout(() => {
      api
        .suggest(q)
        .then((s) => {
          setOptions(s);
          setOpen(true);
          setActive(-1);
        })
        .catch(() => setOptions([]));
    }, 150);
    return () => clearTimeout(id);
  }, [text, picked]);

  const label = (s: { slug: string; name: string }) => (lang === "es" ? SERVICE_ES[s.slug] ?? s.name : s.name);

  function choose(s: Suggestion) {
    setPicked({ slug: s.slug, name: s.name, code_system: s.code_system, code: s.code });
    setText(s.name);
    setOpen(false);
    setError(null);
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || options.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(options.length - 1, a + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      choose(options[active]!);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  function useLocation() {
    if (!("geolocation" in navigator)) {
      setError(t.locationDenied);
      return;
    }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        // two decimals (about half a mile) is enough for a 25-mile search
        coords.current = { lat: pos.coords.latitude.toFixed(2), lng: pos.coords.longitude.toFixed(2) };
        setZip("");
        setBusy(false);
        setError(null);
      },
      () => {
        setBusy(false);
        setError(t.locationDenied);
      },
      { maximumAge: 600000, timeout: 10000 },
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    let service = picked && text === picked.name ? picked : null;
    if (!service && options.length === 1) service = { ...options[0]! };
    if (!service) {
      setError(t.pickService);
      return;
    }
    const params = new URLSearchParams(
      service.code && service.code_system ? { code_system: service.code_system, code: service.code } : { service: service.slug },
    );
    if (kinds.length) params.set("type", kinds.join(","));
    if (radius !== "25") params.set("r", radius);
    if (paying === "plan") {
      if (!insurance) {
        setError(t.insurerPick);
        return;
      }
      params.set("mode", "plan");
      if ("plan" in insurance) params.set("plan", insurance.plan);
      else params.set("payer", insurance.payer);
    }
    if (coords.current && !zip) {
      params.set("lat", coords.current.lat);
      params.set("lng", coords.current.lng);
    } else {
      if (!/^\d{5}$/.test(zip)) {
        setError(t.badZip);
        return;
      }
      setBusy(true);
      try {
        const p = await api.zip(zip);
        setPlace(p);
      } catch {
        setBusy(false);
        setError(t.zipNotFound);
        return;
      }
      params.set("zip", zip);
    }
    setBusy(false);
    router.push(`/search?${params.toString()}`);
  }

  return (
    <form className={compact ? "search compact" : "search"} onSubmit={submit} role="search" noValidate>
      <div className="field grow">
        <label htmlFor={`${listId}-what`}>{t.whatLabel}</label>
        <div className="input-icon">
          <Search size={20} />
          <input
            id={`${listId}-what`}
            role="combobox"
            aria-expanded={open && options.length > 0}
            aria-controls={`${listId}-list`}
            aria-autocomplete="list"
            aria-activedescendant={active >= 0 ? `${listId}-opt-${active}` : undefined}
            autoComplete="off"
            placeholder={t.whatPlaceholder}
            value={picked && text === picked.name ? label(picked) : text}
            onChange={(e) => {
              setText(e.target.value);
              setPicked(null);
            }}
            onKeyDown={onKey}
            onFocus={() => options.length && setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
          />
        </div>
        {open && options.length > 0 && (
          <ul className="suggest" id={`${listId}-list`} role="listbox">
            {options.map((o, i) => (
              <li
                key={o.slug}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? "on" : ""}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(o);
                }}
              >
                <span>{o.kind === "code" ? `${o.matched} · ${o.name}` : label(o)}</span>
                {o.kind === "code" ? (
                  <span className="suggest-why">{t.codeTag}</span>
                ) : (
                  o.matched !== o.name && <span className="suggest-why">“{o.matched}”</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="field zip">
        <label htmlFor={`${listId}-zip`}>{t.whereLabel}</label>
        <div className="input-icon">
          <Pin size={20} />
          <input
            id={`${listId}-zip`}
            inputMode="numeric"
            autoComplete="postal-code"
            maxLength={5}
            placeholder={t.wherePlaceholder}
            value={zip}
            onChange={(e) => {
              setZip(e.target.value.replace(/\D/g, ""));
              coords.current = null;
            }}
          />
        </div>
      </div>
      <div className="field radius">
        <label htmlFor={`${listId}-r`}>{t.radiusLabel}</label>
        <select id={`${listId}-r`} value={radius} onChange={(e) => setRadius(e.target.value)}>
          {RADII.map((r) => (
            <option key={r} value={r}>
              {fill(t.withinMiles, { r })}
            </option>
          ))}
        </select>
      </div>
      {!compact && types.length > 0 && (
        <div className="field type">
          <label htmlFor={`${listId}-type`}>{t.typeLabel}</label>
          <TypePicker id={`${listId}-type`} types={types} value={kinds} onChange={setKinds} />
        </div>
      )}
      {!compact && (
        <fieldset className="field paying">
          <legend>{t.payingHow}</legend>
          <div className="segmented two" role="radiogroup">
            {(["cash", "plan"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={paying === m}
                className={paying === m ? "seg on" : "seg"}
                onClick={() => setPaying(m)}
              >
                {m === "cash" ? t.modeCash : t.modePlan}
              </button>
            ))}
          </div>
          {paying === "plan" && (
            <div className="insurer">
              <label htmlFor={`${listId}-ins`} className="sr">
                {t.insurerLabel}
              </label>
              <InsurancePicker id={`${listId}-ins`} value={insurance} onChange={setInsurance} />
            </div>
          )}
        </fieldset>
      )}
      <button className="btn primary search-btn" type="submit" disabled={busy}>
        <Search size={20} /> <span>{t.searchBtn}</span>
      </button>
      <div className="search-foot">
        <button type="button" className="link-btn" onClick={useLocation} disabled={busy}>
          <Locate size={16} /> {busy ? t.locating : coords.current && !zip ? "✓ " + t.useLocation : t.useLocation}
        </button>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </div>
    </form>
  );
}

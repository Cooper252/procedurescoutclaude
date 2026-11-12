"use client";

// "Type of facility": tick one or several (hospitals AND surgery centers AND
// medical spas...), or none for all of them (Cooper, 2026-11-12).

import { useEffect, useRef, useState } from "react";
import { fill, GROUP_ES, TYPE_ES } from "@/lib/i18n";
import type { ProviderType } from "@/lib/types";
import { useApp } from "./AppState";

export function TypePicker({
  id,
  types,
  value,
  onChange,
}: {
  id: string;
  types: ProviderType[];
  value: string[];
  onChange: (next: string[]) => void;
}) {
  const { t, lang } = useApp();
  const ref = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  const name = (ty: ProviderType) => (lang === "es" ? TYPE_ES[ty.code] ?? ty.name : ty.name);
  const groups = [...new Set(types.map((ty) => ty.grouping ?? "Other"))];

  // close when clicking anywhere else
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const summary =
    value.length === 0
      ? t.typeAny
      : value.length === 1
        ? name(types.find((ty) => ty.code === value[0]) ?? { code: value[0]!, name: value[0]! })
        : fill(t.typeSome, { n: String(value.length) });

  function toggle(code: string) {
    onChange(value.includes(code) ? value.filter((c) => c !== code) : [...value, code]);
  }

  return (
    <details
      ref={ref}
      className="type-picker"
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary id={id} aria-label={`${t.typeLabel}: ${summary}`}>
        <span>{summary}</span>
      </summary>
      <div className="type-menu" role="group" aria-labelledby={id}>
        <label className="check type-all">
          <input type="checkbox" checked={value.length === 0} onChange={() => onChange([])} /> {t.typeAny}
        </label>
        {groups.map((g) => (
          <fieldset key={g} className="type-group">
            <legend>{lang === "es" ? GROUP_ES[g] ?? g : g}</legend>
            {types
              .filter((ty) => (ty.grouping ?? "Other") === g)
              .map((ty) => (
                <label key={ty.code} className="check">
                  <input type="checkbox" checked={value.includes(ty.code)} onChange={() => toggle(ty.code)} /> {name(ty)}
                </label>
              ))}
          </fieldset>
        ))}
        {value.length > 0 && (
          <button type="button" className="link-btn" onClick={() => onChange([])}>
            {t.typeClear}
          </button>
        )}
      </div>
    </details>
  );
}

export function parseTypes(raw: string | null | undefined): string[] {
  return (raw ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter((s) => /^[a-z][a-z_]{1,40}$/.test(s));
}

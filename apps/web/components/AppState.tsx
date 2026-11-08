"use client";

// Site-wide state kept in memory while the person moves between pages:
// language, the place they searched and their free-care answers. Income and
// household size are never sent in a URL or saved; only the language choice
// is remembered on this device.

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { DICTS, type Dict, type Lang } from "@/lib/i18n";
import type { Place } from "@/lib/types";

interface CareAnswers {
  householdSize: number;
  income: string;
}

interface State {
  lang: Lang;
  t: Dict;
  setLang: (l: Lang) => void;
  place: Place | null;
  setPlace: (p: Place | null) => void;
  care: CareAnswers | null;
  setCare: (c: CareAnswers | null) => void;
}

const Ctx = createContext<State | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  const [place, setPlace] = useState<Place | null>(null);
  const [care, setCare] = useState<CareAnswers | null>(null);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("ps-lang");
      if (saved === "es" || saved === "en") setLangState(saved);
      else if (navigator.language.toLowerCase().startsWith("es")) setLangState("es");
    } catch {
      /* storage blocked: stay in English */
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo<State>(
    () => ({
      lang,
      t: DICTS[lang],
      setLang: (l) => {
        setLangState(l);
        try {
          window.localStorage.setItem("ps-lang", l);
        } catch {
          /* ignore */
        }
      },
      place,
      setPlace,
      care,
      setCare,
    }),
    [lang, place, care],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): State {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp outside AppStateProvider");
  return v;
}

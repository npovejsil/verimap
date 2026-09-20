import { useStore } from "../store";
import { en, type Key, type Table } from "./strings";
import { ar } from "./ar";
import { bn } from "./bn";
import { es } from "./es";
import { fr } from "./fr";
import { hi } from "./hi";
import { id } from "./id";
import { pt } from "./pt";
import { ru } from "./ru";
import { zh } from "./zh";

/** The UN's six official languages, plus the four most spoken after them.
 *  Each is named in its own script -- a reader looking for their language is
 *  not helped by seeing it written in English. */
export const LANGUAGES = [
  { code: "en", label: "English", rtl: false },
  { code: "ar", label: "العربية", rtl: true },
  { code: "zh", label: "中文", rtl: false },
  { code: "fr", label: "Français", rtl: false },
  { code: "ru", label: "Русский", rtl: false },
  { code: "es", label: "Español", rtl: false },
  { code: "hi", label: "हिन्दी", rtl: false },
  { code: "pt", label: "Português", rtl: false },
  { code: "bn", label: "বাংলা", rtl: false },
  { code: "id", label: "Bahasa Indonesia", rtl: false },
] as const;

export type Locale = (typeof LANGUAGES)[number]["code"];

const TABLES: Record<Locale, Table> = { en, ar, zh, fr, ru, es, hi, pt, bn, id };

export const isRtl = (locale: Locale) =>
  LANGUAGES.find((l) => l.code === locale)?.rtl ?? false;

/** Locale tags for Intl. The interface language also drives number formatting,
 *  so 1,234.5 renders the way the reader expects rather than the way en-US
 *  does. */
const INTL: Record<Locale, string> = {
  en: "en", ar: "ar", zh: "zh", fr: "fr", ru: "ru",
  es: "es", hi: "hi", pt: "pt", bn: "bn", id: "id",
};

function fill(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    name in vars ? String(vars[name]) : whole,
  );
}

export interface Translator {
  t: (key: Key, vars?: Record<string, string | number>) => string;
  /** Locale-aware number formatting, replacing bare toLocaleString(). */
  n: (value: number, decimals?: number) => string;
  locale: Locale;
  rtl: boolean;
}

export function useT(): Translator {
  const locale = useStore((s) => s.locale);
  const table = TABLES[locale] ?? en;
  return {
    locale,
    rtl: isRtl(locale),
    // English is the fallback for any key a translation has not covered, so a
    // partial translation degrades to mixed language rather than to blanks.
    t: (key, vars) => fill(table[key] ?? en[key] ?? key, vars),
    n: (value, decimals) =>
      new Intl.NumberFormat(INTL[locale], {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value),
  };
}

/** Indicator names and hazard-measure names, translated where available. */
export function translated(
  table: Record<string, string>,
  locale: Locale,
  overrides: Partial<Record<Locale, Record<string, string>>>,
  code: string,
  fallback?: string,
): string {
  return overrides[locale]?.[code] ?? table[code] ?? fallback ?? code;
}

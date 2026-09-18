import { useEffect, useState } from "react";
import {
  loadAdm1,
  loadCountryDetail,
  stemOf,
  type AdminLevel,
  type HazardDetail,
} from "./data/hazard";

const nameFiles: Record<AdminLevel, string> = {
  1: "boundaries/adm1.names.json",
  2: "boundaries/adm2.names.json",
};

const namesCache: Partial<Record<AdminLevel, Record<string, string>>> = {};
/** ucode without its trailing _V<n>, so a version mismatch still resolves. */
const stemCache: Partial<Record<AdminLevel, Record<string, string>>> = {};

async function loadNames(level: AdminLevel): Promise<Record<string, string>> {
  if (namesCache[level]) return namesCache[level]!;
  let names: Record<string, string> = {};
  try {
    const response = await fetch(nameFiles[level]);
    if (response.ok) names = await response.json();
  } catch {
    names = {};
  }
  namesCache[level] = names;
  // The hazard database cites whichever boundary version was current when it
  // was built -- Solomon Islands records say V2 while GeoRepo's latest is V3 --
  // so fall back to matching on the versionless stem.
  const stems: Record<string, string> = {};
  for (const [ucode, name] of Object.entries(names)) {
    stems[stemOf(ucode)] ??= name;
  }
  stemCache[level] = stems;
  return names;
}

export interface CountryDetail {
  detail: HazardDetail | null;
  loading: boolean;
  /** Place name for a ucode or a stem; falls back to the raw code when the
   *  names file hasn't been built. */
  nameFor: (code: string) => string;
}

/** Hazard records plus place names for one country at one admin level.
 *
 *  Admin-2 comes from that country's chunk; admin-1 from the single rolled-up
 *  file. Both are memoised, and both arrive in the same shape, so the map, the
 *  ranked bars and the detail readout never branch on level. */
export function useHazardDetail(
  iso3: string | null,
  level: AdminLevel = 2,
): CountryDetail {
  const [detail, setDetail] = useState<HazardDetail | null>(null);
  const [, setLoaded] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!iso3) {
      setDetail(null);
      return;
    }
    let live = true;
    setLoading(true);
    const records =
      level === 1
        ? loadAdm1().then((all) => all[iso3] ?? null)
        : loadCountryDetail(iso3);
    Promise.all([records, loadNames(level)])
      .then(([d]) => {
        if (!live) return;
        setDetail(d);
        setLoaded((n) => n + 1);
      })
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [iso3, level]);

  const nameFor = (code: string) =>
    namesCache[level]?.[code] ?? stemCache[level]?.[stemOf(code)] ?? code;

  return { detail, loading, nameFor };
}

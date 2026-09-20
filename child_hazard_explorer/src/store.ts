import { create } from "zustand";
import type { AdminLevel } from "./data/hazard";
import type { Locale } from "./i18n";

/** Compact catalog shape. Keys are short because the full crawl is ~46 MB and
 *  repeats every variable name under many branches; names live once in
 *  `Catalog.names` and the tree references them by dcid. */
export interface CatalogNode {
  /** dcid */
  d: string;
  /** display name */
  n: string;
  /** children */
  c?: CatalogNode[];
  /** variable dcids at this node */
  v?: string[];
  /** goal number, on goal roots only */
  g?: number;
}

export interface Catalog {
  source: string;
  built: string;
  goals: CatalogNode[];
  names: Record<string, string>;
}

export interface PlaceInfo {
  name: string;
  iso3: string;
  continent: string | null;
}

export interface Places {
  continents: { dcid: string; name: string; countries: string[] }[];
  countries: Record<string, PlaceInfo>;
}

interface State {
  /** SDG catalog. The app is hazard-only now; these are kept because
   *  GoalNav.tsx and the SDG ETL still compile against them. */
  catalog: Catalog | null;
  places: Places | null;
  /** Place dcids: countries ("country/KEN") and/or continents ("africa"). */
  selected: string[];
  variable: string | null;
  variableName: string;
  openGoal: number | null;

  hazardIndicator: string;
  hazardMetric: "pct" | "exposed";
  /** One unit at the current level, as a versionless ucode stem
   *  ("KEN_0012_0003"). Shared by the drilldown bars and the map layer so a
   *  pick in either shows in both. */
  selectedArea: string | null;
  /** Interface language. Place names and database field names are not
   *  translated -- they come from the sources in their own language. */
  locale: Locale;
  /** Which level the drilldown paints: 1 = counties (rolled up), 2 = the
   *  units the database actually holds. A country opens at 1. */
  adminLevel: AdminLevel;
  /** Still following the map zoom. Cleared once the user picks a level by
   *  hand, so auto-switching stops fighting them; reset on a new country. */
  adminLevelAuto: boolean;

  setCatalog: (c: Catalog) => void;
  setPlaces: (p: Places) => void;
  togglePlace: (dcid: string) => void;
  clearSelection: () => void;
  setVariable: (dcid: string, name: string) => void;
  setOpenGoal: (goal: number | null) => void;
  setHazard: (indicator: string) => void;
  setHazardMetric: (metric: "pct" | "exposed") => void;
  setSelectedArea: (stem: string | null) => void;
  setAdminLevel: (level: AdminLevel, manual?: boolean) => void;
  setLocale: (locale: Locale) => void;
}

const LOCALE_KEY = "che.locale";

/** A published page may run where storage is blocked, so never let reading or
 *  writing the preference break the app. */
function storedLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_KEY);
    if (saved) return saved as Locale;
  } catch {
    /* private window, blocked site data: fall through to English */
  }
  return "en";
}

export const useStore = create<State>((set) => ({
  catalog: null,
  places: null,
  selected: [],
  variable: null,
  variableName: "",
  openGoal: null,
  hazardIndicator: "PM25",
  hazardMetric: "pct",
  selectedArea: null,
  adminLevel: 1,
  adminLevelAuto: true,
  locale: storedLocale(),

  setCatalog: (catalog) => set({ catalog }),
  setPlaces: (places) => set({ places }),

  togglePlace: (dcid) =>
    set((s) => ({
      selected: s.selected.includes(dcid)
        ? s.selected.filter((d) => d !== dcid)
        : [...s.selected, dcid],
      // The drilldown belongs to one country; changing the country retires it
      // and returns the level to counties, following the zoom again. The
      // language is not part of that: it is the reader's choice, not the
      // selection's.
      selectedArea: null,
      adminLevel: 1,
      adminLevelAuto: true,
    })),

  clearSelection: () =>
    set({ selected: [], selectedArea: null, adminLevel: 1, adminLevelAuto: true }),
  setVariable: (variable, variableName) => set({ variable, variableName }),
  setOpenGoal: (openGoal) => set({ openGoal }),
  setHazard: (hazardIndicator) => set({ hazardIndicator }),
  setHazardMetric: (hazardMetric) => set({ hazardMetric }),
  setSelectedArea: (selectedArea) => set({ selectedArea }),

  setLocale: (locale) => {
    try {
      localStorage.setItem(LOCALE_KEY, locale);
    } catch {
      /* not fatal: the choice just will not survive a reload */
    }
    set({ locale });
  },

  // Changing level drops the selection: a county stem means nothing to the
  // sub-county layer, and a stale outline would just never match.
  setAdminLevel: (adminLevel, manual = false) =>
    set((s) =>
      s.adminLevel === adminLevel
        ? manual && s.adminLevelAuto
          ? { adminLevelAuto: false }
          : {}
        : {
            adminLevel,
            selectedArea: null,
            adminLevelAuto: manual ? false : s.adminLevelAuto,
          },
    ),
}));

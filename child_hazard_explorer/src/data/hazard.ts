/**
 * UNICEF Global Child Hazard Database, served as static JSON.
 *
 * The Solr core behind this sends no CORS headers and needs HTTP Basic auth, so
 * the browser never talks to it. `etl/build_hazard.py` aggregates it at build
 * time; these files carry no credentials.
 */

export interface HazardCell {
  exposed: number;
  pop: number;
  pct: number | null;
  hazard: number | null;
  worst: number | null;
  cls: number | null;
  units: number;
}

export interface HazardCountries {
  indicators: string[];
  countries: Record<string, { records: number; indicators: Record<string, HazardCell> }>;
}

/** Admin-2 detail for one country, stored columnar to keep files small.
 *  `cls` is the country exposure class, 1-5. */
export interface HazardDetail {
  iso3: string;
  areas: string[];
  indicators: Record<
    string,
    {
      area: number[];
      exposed: (number | null)[];
      pop: (number | null)[];
      pct: (number | null)[];
      hazard: (number | null)[];
      cls: (number | null)[];
      /** Admin-1 only: how many admin-2 children the cell was computed from,
       *  and how many the parent has. Coverage is uneven, so a value can come
       *  from a subset and must say so. */
      units?: number[];
      total?: number[];
    }
  >;
}

/** Which boundary level the drilldown is painting. The database is admin-2
 *  only; admin-1 is rolled up from it by `etl/build_adm1_hazard.py`. */
export type AdminLevel = 1 | 2;

/** Everything the database holds about one admin-2 unit for one indicator. */
export interface AreaFacts {
  ucode: string;
  exposed: number | null;
  pop: number | null;
  pct: number | null;
  hazard: number | null;
  cls: number | null;
  /** Set only for a rolled-up admin-1 cell. */
  units?: number;
  total?: number;
}

/** What hazard_mean measures, per indicator: the name that goes in front of the
 *  unit. The unit itself is never written here -- it comes from the database via
 *  data/hazard/units.json, because it differs per indicator (metres, micrograms,
 *  heatwaves a year). Anything not named here reads as "Hazard (mean)". */
export const HAZARD_MEASURE: Record<string, string> = {
  AGRICULTURAL_STRESS: "Agricultural stress index",
  COASTAL_FLOOD: "Coastal flood presence",
  COMPLEX_EMERGENCIES_ACLED: "Conflict intensity",
  EARTHQUAKE_0P09: "Peak ground acceleration",
  EARTHQUAKE_0P34: "Peak ground acceleration",
  EXTREME_HOT_DAYS: "Days above 35 °C",
  FIRE_FREQUENCY: "Fire frequency",
  FIRE_INTENSITY: "Fire radiative power",
  HEATWAVE_DURATION: "Heatwave duration",
  HEATWAVE_FREQUENCY: "Heatwave frequency",
  HEATWAVE_SEVERITY: "Heatwave severity",
  LANDSLIDES_0P01: "Landslide frequency",
  LANDSLIDES_0P1: "Landslide frequency",
  MALARIA_FALCIPARUM: "Incidence rate",
  MALARIA_VIVAX: "Incidence rate",
  METEOROLOGICAL_DROUGHT_SPEI: "Drought index (SPEI)",
  METEOROLOGICAL_DROUGHT_SPI: "Drought index (SPI)",
  PM25: "PM2.5 concentration",
  RIVER_FLOOD: "Flood depth",
  SDS_SUSCEPTIBILITY: "Dust storm susceptibility",
  WIND_SPEED: "Wind speed",
};

/** What the 22 indicators measure, for labels and tooltips. */
export const HAZARD_LABELS: Record<string, string> = {
  AGRICULTURAL_STRESS: "Agricultural stress",
  COASTAL_FLOOD: "Coastal flood",
  COMPLEX_EMERGENCIES_ACLED: "Complex emergencies",
  EARTHQUAKE_0P09: "Earthquake (0.09g)",
  EARTHQUAKE_0P34: "Earthquake (0.34g)",
  EXTREME_HOT_DAYS: "Extreme hot days",
  FIRE_FREQUENCY: "Fire frequency",
  FIRE_INTENSITY: "Fire intensity",
  HEATWAVE_DURATION: "Heatwave duration",
  HEATWAVE_FREQUENCY: "Heatwave frequency",
  HEATWAVE_SEVERITY: "Heatwave severity",
  LANDSLIDES_0P01: "Landslides (0.01)",
  LANDSLIDES_0P1: "Landslides (0.1)",
  MALARIA_FALCIPARUM: "Malaria (P. falciparum)",
  MALARIA_VIVAX: "Malaria (P. vivax)",
  METEOROLOGICAL_DROUGHT_SPEI: "Drought (SPEI)",
  METEOROLOGICAL_DROUGHT_SPI: "Drought (SPI)",
  PM25: "Air pollution (PM2.5)",
  RIVER_FLOOD: "River flood",
  SDS_SUSCEPTIBILITY: "Sand & dust storms",
  VOLCANOES_100KM_BUFFER: "Volcanoes (100km)",
  WIND_SPEED: "Extreme wind speed",
};

/** The metric shown on the map. Children exposed is the headline number; the
 *  share matters more when comparing countries of different sizes. */
export type HazardMetric = "pct" | "exposed";

export const HAZARD_METRICS: { key: HazardMetric; label: string; unit: string }[] = [
  { key: "pct", label: "Share of children exposed", unit: "%" },
  { key: "exposed", label: "Children exposed", unit: "children" },
];

/** A ucode without its trailing _V<n>.
 *
 *  The hazard database cites whichever boundary version was current when it was
 *  built, which is not always GeoRepo's latest -- see README trap 3 -- so every
 *  join between hazard records and boundaries goes through the stem. */
export const stemOf = (ucode: string) => ucode.replace(/_V\d+$/, "");

let cache: HazardCountries | null = null;

export async function loadHazard(): Promise<HazardCountries> {
  if (cache) return cache;
  const response = await fetch("hazard/countries.json");
  if (!response.ok) throw new Error(`hazard data ${response.status}`);
  cache = (await response.json()) as HazardCountries;
  return cache;
}

let indexCache: Record<string, number> | null = null;
const chunks = new Map<number, Record<string, HazardDetail>>();

/** Admin-2 detail for one country.
 *
 *  `bundle_hazard.py` packs the 229 per-country files into a dozen chunks --
 *  a published artifact may hold at most 255 files -- so a country is reached
 *  through the index, not by a filename of its own. Chunks are memoised: the
 *  map layer and the ranked bars ask for the same country. */
export async function loadCountryDetail(iso3: string): Promise<HazardDetail | null> {
  if (!indexCache) {
    const response = await fetch("hazard/admin2-index.json");
    if (!response.ok) return null;
    indexCache = (await response.json()) as Record<string, number>;
  }
  const chunk = indexCache[iso3];
  if (chunk === undefined) return null;

  let payload = chunks.get(chunk);
  if (!payload) {
    const response = await fetch(`hazard/admin2-${chunk}.json`);
    if (!response.ok) return null;
    payload = (await response.json()) as Record<string, HazardDetail>;
    chunks.set(chunk, payload);
  }
  return payload[iso3] ?? null;
}

let unitsCache: Record<string, string> | null = null;

/** Hazard units per indicator, straight from the database. */
export async function loadUnits(): Promise<Record<string, string>> {
  if (unitsCache) return unitsCache;
  try {
    const response = await fetch("hazard/units.json");
    unitsCache = response.ok ? await response.json() : {};
  } catch {
    unitsCache = {};
  }
  return unitsCache!;
}

/** The full row for one unit, found by stem. Null when the indicator has no
 *  record for it -- coverage is uneven, and 22 indicators do not all reach
 *  every one of the 41,023 units. */
export function areaFacts(
  detail: HazardDetail,
  indicator: string,
  stem: string,
): AreaFacts | null {
  const block = detail.indicators[indicator];
  if (!block) return null;
  for (let i = 0; i < block.area.length; i++) {
    const ucode = detail.areas[block.area[i]];
    if (stemOf(ucode) !== stem) continue;
    return {
      ucode,
      exposed: block.exposed[i] ?? null,
      pop: block.pop?.[i] ?? null,
      pct: block.pct[i] ?? null,
      hazard: block.hazard[i] ?? null,
      cls: block.cls?.[i] ?? null,
      units: block.units?.[i],
      total: block.total?.[i],
    };
  }
  return null;
}

let adm1Cache: Record<string, HazardDetail> | null = null;

/** Admin-1 roll-ups for every country, in the same shape as an admin-2 detail
 *  file, so both levels read through one code path. Small enough (one file,
 *  ~3,990 units worldwide) not to need the chunking the admin-2 data does. */
export async function loadAdm1(): Promise<Record<string, HazardDetail>> {
  if (adm1Cache) return adm1Cache;
  const response = await fetch("hazard/adm1.json");
  if (!response.ok) return (adm1Cache = {});
  adm1Cache = (await response.json()) as Record<string, HazardDetail>;
  return adm1Cache;
}

/** One value per unit, keyed by stem so it joins to the boundaries. */
export function areaValues(
  detail: HazardDetail,
  indicator: string,
  metric: HazardMetric,
): Map<string, number> {
  const out = new Map<string, number>();
  const block = detail.indicators[indicator];
  if (!block) return out;
  const source = metric === "pct" ? block.pct : block.exposed;
  block.area.forEach((areaIndex, i) => {
    const value = source[i];
    if (value === null || !Number.isFinite(value)) return;
    out.set(stemOf(detail.areas[areaIndex]), value as number);
  });
  return out;
}

export function hazardValues(
  data: HazardCountries,
  indicator: string,
  metric: HazardMetric,
): Map<string, number> {
  const out = new Map<string, number>();
  for (const [iso3, entry] of Object.entries(data.countries)) {
    const cell = entry.indicators[indicator];
    if (!cell) continue;
    const value = metric === "pct" ? cell.pct : cell.exposed;
    if (value !== null && Number.isFinite(value)) out.set(iso3, value);
  }
  return out;
}

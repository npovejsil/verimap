/**
 * Client for the UN System Data Commons observation API.
 *
 * Two constraints shape this file.
 *
 * 1. The deployment is federated with the wider Data Commons graph: the same
 *    endpoint answers for other publishers without saying so. `sdg/SI_POV_DAY1`
 *    and `undata/sdg/SI_POV_DAY1` both return 200 for Kenya 2021 -- 36.0 and
 *    46.4 respectively. Only `undata/` is UN-governed, so every request is
 *    guarded.
 *
 * 2. A few country dcids are rejected outright with 403 when they appear
 *    literally in a `nodes=` or `entity.dcids=` parameter -- see BLOCKED below.
 *    They come back perfectly well through an `entity.expression`, so country
 *    data is always fetched in bulk rather than per entity. That is also
 *    faster: all 170 countries with full history is one 89 KB request.
 */

const API = "https://unsd-datacommons.gcp.un-icc.cloud/core/api/v2";

/** Every country in one request. */
const ALL_COUNTRIES = "Earth<-containedInPlace+{typeOf:Country}";

/**
 * Country dcids that return 403 when named directly in a query parameter.
 * Measured, not documented: they fail alone, at any batch size, on both the
 * node and observation endpoints, with any property and any casing -- but they
 * ARE present in the `entity.expression` results above, so this reads like a
 * request-filtering rule on the literal string rather than anything about the
 * data. Never put these in `entity.dcids`.
 */
const BLOCKED = new Set(["country/ESH", "country/GRC", "country/SVN"]);

export const CONTINENTS = [
  { dcid: "africa", name: "Africa" },
  { dcid: "asia", name: "Asia" },
  { dcid: "europe", name: "Europe" },
  { dcid: "northamerica", name: "North America" },
  { dcid: "southamerica", name: "South America" },
  { dcid: "oceania", name: "Oceania" },
];

export interface Observation {
  date: string;
  value: number;
}

export interface Facet {
  unit?: string;
  provenanceId?: string;
  provenanceUrl?: string;
  observationPeriod?: string;
}

export interface PlaceSeries {
  place: string;
  observations: Observation[];
  facet?: Facet;
}

function assertUnScoped(variable: string): void {
  if (!variable.startsWith("undata/")) {
    throw new Error(
      `Refusing to query "${variable}": only undata/ identifiers are UN-governed. ` +
        `Wider-graph variables return different numbers for the same indicator.`,
    );
  }
}

interface RawResponse {
  byVariable: Record<
    string,
    {
      byEntity: Record<
        string,
        { orderedFacets?: { facetId: string; observations: Observation[] }[] }
      >;
    }
  >;
  facets?: Record<string, Facet>;
}

async function request(params: URLSearchParams): Promise<RawResponse> {
  const response = await fetch(`${API}/observation?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`Data Commons ${response.status}: ${response.statusText}`);
  }
  return response.json();
}

function baseParams(variable: string): URLSearchParams {
  const params = new URLSearchParams();
  params.append("variable.dcids", variable);
  for (const field of ["date", "value", "variable", "entity"]) {
    params.append("select", field);
  }
  return params;
}

function unpack(raw: RawResponse, variable: string): PlaceSeries[] {
  const byEntity = raw.byVariable?.[variable]?.byEntity ?? {};
  const facets = raw.facets ?? {};
  const out: PlaceSeries[] = [];
  for (const [place, entry] of Object.entries(byEntity)) {
    // orderedFacets is ranked by the API; the first is the preferred source.
    const best = entry.orderedFacets?.[0];
    if (!best?.observations?.length) continue;
    out.push({ place, observations: best.observations, facet: facets[best.facetId] });
  }
  return out;
}

/**
 * Full history for every country, in one request.
 *
 * Omitting `date` entirely is what returns every observation; passing
 * `date=LATEST` would give only the most recent. Fetching the whole series once
 * means the choropleth, the ranked bars and the trend chart all read from the
 * same response instead of issuing a request each.
 */
export async function fetchWorldSeries(variable: string): Promise<PlaceSeries[]> {
  assertUnScoped(variable);
  const params = baseParams(variable);
  params.append("entity.expression", ALL_COUNTRIES);
  return unpack(await request(params), variable);
}

/**
 * Full history for named places. Used for continents, which the country
 * expression does not cover. Blocked country dcids are dropped rather than
 * allowed to fail the whole request -- their values come from
 * `fetchWorldSeries` instead.
 */
export async function fetchPlaceSeries(
  variable: string,
  places: string[],
): Promise<PlaceSeries[]> {
  assertUnScoped(variable);
  const safe = places.filter((p) => !BLOCKED.has(p));
  if (!safe.length) return [];
  const params = baseParams(variable);
  for (const place of safe) params.append("entity.dcids", place);
  return unpack(await request(params), variable);
}

export function isBlocked(dcid: string): boolean {
  return BLOCKED.has(dcid);
}

export function latestOf(series: PlaceSeries): Observation | undefined {
  return series.observations[series.observations.length - 1];
}

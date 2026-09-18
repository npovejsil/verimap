/**
 * Per-country boundary geometry, served from bundled chunks.
 *
 * Each country's file holds BOTH levels as TopoJSON objects -- `adm2` as the
 * database records them, `adm1` dissolved from it -- sharing one arc pool, so
 * switching level costs no fetch at all. `etl/bundle_boundaries.py` packs the
 * 229 files into chunks to stay under the published-artifact file limit,
 * packed so that opening a country still fetches roughly that country.
 */

export interface CountryTopology {
  objects: Record<string, unknown>;
  [key: string]: unknown;
}

let indexCache: Record<string, number> | null = null;
const chunks = new Map<number, Record<string, CountryTopology>>();
const inflight = new Map<number, Promise<Record<string, CountryTopology>>>();

export async function loadCountryBoundaries(
  iso3: string,
): Promise<CountryTopology | null> {
  if (!indexCache) {
    const response = await fetch("boundaries/country-index.json");
    if (!response.ok) return null;
    indexCache = (await response.json()) as Record<string, number>;
  }
  const chunk = indexCache[iso3];
  if (chunk === undefined) return null;

  let payload = chunks.get(chunk);
  if (!payload) {
    // Share one request when two things ask for the same chunk at once.
    let pending = inflight.get(chunk);
    if (!pending) {
      pending = fetch(`boundaries/country-${chunk}.json`)
        .then((r) => (r.ok ? r.json() : {}))
        .finally(() => inflight.delete(chunk));
      inflight.set(chunk, pending);
    }
    payload = await pending;
    chunks.set(chunk, payload!);
  }
  return payload![iso3] ?? null;
}

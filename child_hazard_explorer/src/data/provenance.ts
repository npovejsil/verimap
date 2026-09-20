/**
 * Where every figure came from, and where the sources disagree.
 *
 * Written by `etl/build_provenance.py` from the artifacts themselves, so this
 * cannot drift from the data the way a hardcoded attribution line can. Absent
 * file is not an error: the panel says provenance was not built.
 */

export interface Source {
  id: string;
  name: string;
  provides: string;
  access: string;
  licence: string;
  reference_period?: string;
  extracted: string | null;
  upstream_modified?: string | null;
  records?: number;
}

export interface FieldTrace {
  /** The label as the readout shows it. */
  shown: string;
  /** The field it is read from in the source. */
  field: string;
}

export interface CrossCheck {
  id: string;
  label: string;
  detail: string;
  agree: number;
  total: number;
  passed: boolean;
  offenders: { iso3?: string; units?: number; indicator?: string; facet?: number; sum?: number }[];
}

export interface CountryProvenance {
  adm2_units: number;
  adm1_areas: number;
  indicators: number;
  facet_agrees: boolean;
  facet_cells: number;
  version_mismatch: number;
  unnamed: number;
}

export interface Provenance {
  generated: string;
  sources: Source[];
  query: { filters: string[]; meaning: string[] };
  fields: FieldTrace[];
  transformations: string[];
  counts: {
    countries: number;
    indicators: number;
    admin2_units: number;
    admin1_areas: number;
  };
  crosschecks: {
    per_country: Record<string, CountryProvenance>;
    checks: CrossCheck[];
  };
}

let cache: Provenance | null = null;

export async function loadProvenance(): Promise<Provenance | null> {
  if (cache) return cache;
  try {
    const response = await fetch("provenance.json");
    if (!response.ok) return null;
    cache = (await response.json()) as Provenance;
    return cache;
  } catch {
    return null;
  }
}

/** The source field behind a readout label, for the per-number trace. */
export function fieldFor(prov: Provenance | null, shown: string): string | undefined {
  return prov?.fields.find((f) => f.shown === shown)?.field;
}

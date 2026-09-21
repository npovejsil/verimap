# Known Issues and Integration Notes

Operational findings for the UN System Data Commons, the UNICEF Global Child
Hazard Database, and UNICEF GeoRepo. Consolidated from four independent
implementations built by the Data Bears team.

A common characteristic runs through most entries: **the request succeeds.**
The response returns HTTP 200, well-formed JSON, and plausible values, with no
warning that the result is incorrect. Three implementations encountered the
publisher-federation issue independently, in three different languages, before
the teams compared notes. As a result, all four required more defensive
handling than a typical API client.

Each entry cites the branch on which it was identified.

---

## 1. Publisher federation and provenance

**The same endpoint serves multiple publishers without distinction.** The
deployment is federated with the wider Data Commons graph. Kenya
`SI_POV_DAY1` returns **36.0** from the wider graph and **46.4** from the
UN-governed one. Both requests return HTTP 200, and neither response indicates
which source was used.
*jim-xu-draft, nora/map-prototype, shikha/ground-truth-demo,
yiwen/child_hazard_explorer*

Recommendation: treat only `undata/`-prefixed identifiers as authoritative, and
do not construct them by hand. Use the MCP tools for discovery; use the REST
API only to traverse structural paths from identifiers already resolved.

**`search_indicators` returns only `undata/*` variables.** The MCP layer
enforces the UN statistical boundary, so legitimate base Data Commons variables
are not discoverable through it. `Annual_Generation_Electricity` is UN-sourced
(UNSD Energy Statistics) but had to be resolved through the REST `/node`
endpoint. Where a variable is resolved outside the curated namespace, record
how it was resolved and surface that provenance to the reader.
*nora/map-prototype*

---

## 2. Requests that succeed without returning valid data

**An unrecognised variable identifier returns an empty HTTP 200, not an
error.** Discovery should follow three steps: `search_indicators` →
`get_variable_metadata` → `get_observations`. Identifiers must be resolved
rather than hardcoded, as a plausible but incorrect identifier fails silently.
*shikha/ground-truth-demo, yiwen/child_hazard_explorer*

**Batched `node` requests truncate without indication.** Pagination applies
across the entire batch, so a node whose arcs exceed the limit is returned
present but empty. A request for 40 topics returned 40 keys, of which **26 were
empty**. Only a top-level `nextToken` indicates that truncation occurred.
*yiwen/child_hazard_explorer*

**`get_child_observations` returns entity names truncated, with the
observation data complete.** A request for `undata/sdg/EG_ACS_ELEC` across all
countries returned all 217 entities and all 5,400 observations, but only the
first 157 entity names; every identifier from `country/POL` onward carried an
empty `name`. The cut is alphabetical by DCID and total after that point,
which is the signature of a truncated lookup rather than missing source data.
Nothing in the response indicates it. Code that labels a chart from
`entityMetadata` will silently render unlabelled rows for the tail of the
alphabet. Verify name coverage against the observation set, and resolve any
missing names separately.
*shikha/ground-truth-demo, 20 September 2026*

**Date range parameters require `date="range"`.** Supplying
`date_range_start` / `date_range_end` while `date` remains `"latest"` returns
only the latest observation, without error.
*shikha/ground-truth-demo*

---

## 3. Identifier resolution

**Place-name resolution returns HTTP 500 for unresolvable names.** The service
falls back to a Google Maps legacy API that is not enabled on this deployment.
`"Vietnam"` resolves; `"Viet Nam"`, the official UN spelling, returns 500, as
does `"Turkiye"`. A single unresolvable name causes the entire batch to fail,
so places should be resolved individually. Reported to the organisers during
the event.
*shikha/ground-truth-demo*

**Three country identifiers are rejected.** `country/ESH`, `country/GRC` and
`country/SVN` return HTTP 403 when passed literally in a `nodes=` or
`entity.dcids=` parameter, but resolve correctly through an
`entity.expression`. The behaviour is consistent with request filtering on the
literal string.
*yiwen/child_hazard_explorer*

**Search accepts human-readable names; observation calls require DCIDs.**
Search for `Kenya`, then request observations for `country/KEN`.
*shikha/ground-truth-demo*

**`get_variable_metadata` limits `entity_dcids` to 10.** Larger requests return
`400 — entity_dcids cannot exceed 10`. Requests should be chunked and the
resulting facet lists merged on facet `id`, so that a facet spanning two chunks
is not double-counted.
*shikha/ground-truth-demo*

---

## 4. Units and facet selection

**Facet ordering can mix units across countries within a single variable.**
`Annual_Generation_Electricity` lists an EIA facet in **GigawattHour** first
for the United States, and a UNSD facet in **KilowattHour** for the remaining
227 countries. Selecting the preferred facet per country therefore renders the
United States three orders of magnitude — a factor of 10⁶ — from its true
value, accompanied only by a generic multi-facet warning.

Recommendation: pin the facet by unit. Countries with no facet in the selected
unit should be excluded rather than converted implicitly; a reduced set of
countries is preferable to a silently inconsistent one.
*nora/map-prototype*

**Do not combine indicators without verifying units.** The validation layer
returns a `Finding` rather than raising an exception or passing silently, and
views render findings rather than suppressing them. Two rules follow: rows are
never dropped silently, and incompatible units are never combined.
*jim-xu-draft*

---

## 5. Denominators and aggregation

**Select a denominator that reflects the quantity being measured.**
Transmission losses computed against domestic generation yield 92.6% for
Jersey and 59.5% for Andorra, both of which import most of their electricity.
Computed against total supply, the figures are 5.9% and 11.0% respectively.
Germany then returns 4.8%, the United States 4.5% and India 15.4%, consistent
with published figures.
*nora/map-prototype*

**A missing optional term is not necessarily zero.** A country with no recorded
trade in any year has an isolated grid, for which zero is correct. Palestine
and Djibouti, however, import most of their electricity and have gaps in their
import series; treated as zero, both returned losses above 100% of supply.
A missing value should be treated as a gap wherever the term is material for
that country — defined here as a median contribution above 5% across the years
it is reported. Applying the rule to all optional terms rather than material
ones discarded approximately 1,000 country-years, as trade reporting is sparse
in earlier years.
*nora/map-prototype*

**Do not average percentages across places.** World-level figures should be
computed as totals over totals, or as sums, rather than as the mean of
per-country percentages, which weights a small grid equally with a large one.
Both should be gated on coverage: 95% for a sum and 90% for a ratio, since a
missing tenth of total supply shifts an average only slightly but reduces a
total proportionally.
*nora/map-prototype*

**A bounded metric can produce a convergence signal artificially.** Where a
metric is capped at 100%, beta-convergence yields a negative coefficient
mechanically, as does uncorrelated noise through regression to the mean.
Saturated places should be excluded from slope fitting and reported separately,
as their apparent trend reflects the ceiling rather than progress. The
coefficient should be presented together with both caveats.
*jim-xu-draft*

**Annual country series are serially correlated**, so ordinary least squares
standard errors are understated. Use HAC (Newey–West) standard errors.
*jim-xu-draft*

**A saturated series varies through rounding rather than methodology.** Any
self-consistency test therefore requires an absolute floor; without one,
countries closest to the target rank as least reliable. In testing, Brazil
ranked highest for instability at 99.8% access — an artefact of the test rather
than a finding.
*shikha/ground-truth-demo*

---

## 6. Cross-registry identifier joins

**`ref_area` in the hazard data and `ucode` in GeoRepo are the same identifier,
but version suffixes may differ** (for example `SLB_0001_0001_V2` against
`_V3`). Filtering to `is_latest` and joining on the full ucode excludes every
Solomon Islands unit, while the global join rate still reports 99.88%. Join on
the versionless stem.
*shikha/ground-truth-demo, yiwen/child_hazard_explorer*

**The hazard database contains no geometry and no place names** — only
`ref_area` codes such as `KEN_0030_0008_V1`. GeoRepo publishes the same
identifier format, so the join is direct, and its `name` / `name_en` fields
supply the missing unit names. Two access routes are available:

- **Live API** — <https://georepo.unicef.org>. SSO authentication, viewer
  access granted per user, followed by a self-service API key. Documentation is
  available at `/api/v1/docs/` after sign-in. Access is arranged through
  UNICEF's GIS team.
- **Public static mirror, no key required** —
  <https://github.com/unicef-drp/georepo-data> documents GeoJSON exports hosted
  on Azure Blob Storage under CC BY 4.0. Sizes as of 16 September 2026: adm0
  224 MB, adm1 539 MB, adm2 1.41 GB. Each file is a FeatureCollection with one
  feature per line and can therefore be streamed rather than loaded in full.
  Filter on `is_latest = true`, as every historical version of every boundary is
  included, and match `adm0_ucode` to scope to a single country before parsing
  geometry. Coordinate system EPSG:4326. Attribution to "UNICEF GeoRepo" is
  required.

*shikha/ground-truth-demo*

---

## 7. Scope and limitations of the hazard database

- **Single reference year.** All 5,415,036 records carry `time_period: 2025`.
  The dataset is a snapshot; no time series is available at any level.
- **Single administrative level.** All records carry `admin_level: 2`. Admin-1
  figures must be derived, and **4,706 admin-1 areas are aggregated from only a
  subset of their child units**. A partial aggregate is indistinguishable from a
  complete one unless labelled, so coverage should be stated in the readout.
- **Uneven coverage.** An area with no record is not a measurement of zero
  exposure. No-data areas should be rendered distinctly and counted in the
  legend.
- **Additional dimensions.** The database also disaggregates by sex and by
  all-ages against children. These should be pinned explicitly (`sex:_T`,
  `age:Y0T17`, with error-status rows excluded) to avoid combining
  populations.
- **The Solr endpoint cannot be called from a browser.** It returns no CORS
  headers, and its credentials must not be exposed to a client. Query it at
  build time only.

*yiwen/child_hazard_explorer*

---

## 8. Silent failures in third-party tooling

**mapshaper's `-clean` removes polygons and reports the loss only as a count.**
Simplifying admin-2 boundaries with `-clean` returned 106 of Saint Lucia's 556
units, with exit code 0 and valid TopoJSON output. `-clean allow-overlaps`
preserves them. Input and output counts should be compared per country, and the
build should fail on any reduction.
*yiwen/child_hazard_explorer*

**A build step that relocates files should be assumed to have broken its
consumers.** Packing per-country files into chunks and removing the source
directory left the client requesting the original path and rendering the
resulting 404 as the ordinary message "No subnational detail". The
corresponding verification was guarded on `if dir.exists()` and silently
stopped running.
*yiwen/child_hazard_explorer*

**MapLibre's default build loads its worker from a `blob:` URL**, which is
blocked by the Content-Security-Policy applied to published pages. The map
renders blank with no diagnostic output. Use MapLibre's CSP build, which emits
the worker as a standard asset.
*yiwen/child_hazard_explorer*

---

## 9. Payload size constraints

**Inlining all admin-2 geometry is not viable.** Country outlines require
approximately 39.5 bytes per coordinate at full floating-point precision. At 40
coordinates per unit, Egypt's 404 units total approximately 0.6 MB, but all
11,662 units would total approximately 18 MB against a base page of 333 KB.
Rounding coordinates to three decimal places — approximately 100 m, well within
the tolerance of a choropleth — reduces this by roughly half.
*shikha/ground-truth-demo*

**Published artifacts are limited to 255 files and 64 MB.** An unoptimised
build of the hazard explorer produced 501 files and 132 MB; the released bundle
is 164 files and 54.2 MB. The reduction was achieved by removing retired
artifacts, storing both boundary levels in a single shared-arc file per
country, chunking, and reducing stored numeric precision. Chunks should be
packed largest-first so that opening a country retrieves approximately that
country's data rather than an arbitrary fraction of the global set.
*yiwen/child_hazard_explorer*

---

## 10. Additional observations

- **IPUMS is not available on this instance.** No source node or provenance
  record exists under any spelling.
- **World Bank data is available** — six datasets including World Development
  Indicators, covering 1960–2024, reachable in the same manner as other base
  Data Commons variables.
- **Generated JavaScript data files should be ASCII-escaped.** They load as
  classic `<script>` elements, and most servers serve `.js` without a charset
  declaration, causing UTF-8 place names to render incorrectly.
- **The hazard core contains scientific units** such as `days >35°C`,
  `km⁻²·yr⁻¹` and `μg/m³`. Specify UTF-8 encoding explicitly on all file
  handles and output streams.

*nora/map-prototype, yiwen/child_hazard_explorer*

---

## Summary

None of the issues above surfaced as errors. Each returned a successful
response containing incorrect, incomplete, or misattributed data.

Four independent implementations converged on the same set of controls: render
validation findings rather than suppressing them; pin units and exclude
non-conforming records rather than converting implicitly; report the magnitude
and provenance of a disagreement rather than selecting a preferred source;
state explicitly when a figure is derived rather than recorded; and gate builds
on checks that fail loudly when a join silently stops matching.

A plausible result is not evidence of a correct one. Where a figure matters,
verify it against a value derived independently.

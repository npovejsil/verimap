/**
 * Every string the interface shows, in English.
 *
 * This table is the source of truth: a locale file is a partial map over these
 * keys, so anything untranslated falls back to English rather than rendering
 * blank. `{name}` placeholders are filled by `t(key, vars)`.
 *
 * NOT here, deliberately:
 *  - place names (249 countries, 40,641 areas) come from GeoRepo in English;
 *  - the database field names in the lineage panel are literal identifiers in
 *    the source, and translating them would break the verification they exist
 *    for;
 *  - the lineage panel's source descriptions and transformation notes are data,
 *    generated into provenance.json by the ETL.
 */
export const en = {
  "app.title": "Child Hazard Explorer",
  "app.subtitle": "UNICEF Global Child Hazard Database · children 0–17 · 2025",

  "header.selection": "Selection",
  "header.language": "Language",
  "header.chooseCountry": "Choose a country…",
  "header.clear": "Clear ({count})",
  "header.hint": "Click a country to open its areas, then click an area for detail.",
  "header.hintNoMap": "The map is unavailable in this browser — choose a country above.",

  "map.loading": "Loading…",
  "map.legendTitle": "Latest value",
  "map.legendTitleUnit": "Latest value ({unit})",
  "map.noData": "No data ({count})",
  "map.countries": "{count} countries · click one to zoom in",
  "map.areas": "{count} admin-{level} areas in {iso3} · click one for detail",
  "map.reset": "Reset view",
  "map.needsWebgl": "This map needs WebGL",
  "map.webglHelp": "Your browser has it turned off or unavailable. Switching on hardware acceleration, or opening this in another browser, usually fixes it.",
  "map.webglRest": "Everything else on this page still works — pick a country above to see its areas ranked and read the numbers for any one of them.",
  "map.noBoundaries": "No boundaries for {iso3} yet — the map is showing the country outline only.",
  "map.source": "Source: UNICEF Global Child Hazard Database · children 0–17, 2025 · boundaries UNICEF GeoRepo (CC BY 4.0)",

  "level.admin1": "Admin 1",
  "level.admin2": "Admin 2",

  "panel.subnational": "Subnational detail",
  "panel.subnationalAdm1": "Admin-1 areas, rolled up from the admin-2 records",
  "panel.subnationalAdm2": "Admin-2 units, as the database holds them",
  "panel.compared": "Countries compared",
  "panel.showTable": "Show table",
  "panel.showChart": "Show chart",
  "panel.clear": "Clear",
  "panel.place": "Place",
  "panel.country": "Country",
  "panel.value": "Value",
  "panel.year": "Year",

  "stat.exposed": "Exposed children",
  "stat.exposure": "Exposure",
  "stat.population": "Children in area",
  "stat.class": "Exposure class",
  "stat.hazard": "Hazard (mean)",

  "readout.recorded": "as recorded in the database",
  "readout.calculated": "calculated from {units} of {total} admin-2 units",
  "readout.calculatedRest": " — the rest have no record for this indicator",
  "readout.noRecord": "No {indicator} record for this unit.",

  "bars.top": "Top {n} of {total} admin-{level} areas in {iso3} · click a bar to find it on the map",
  "bars.none": "No values for this selection.",
  "bars.loading": "Loading admin-{level} detail…",
  "bars.noCountry": "No subnational detail for {iso3}.",
  "bars.noIndicator": "No {indicator} data for {iso3}.",

  "metric.pct": "Share of children exposed",
  "metric.exposed": "Children exposed",

  "sources.title": "Sources & lineage",
  "sources.show": "Show",
  "sources.hide": "Hide",
  "sources.missing": "Provenance was not built — run {command}.",
  "sources.summary": "{units} admin-2 units · {areas} admin-1 areas · {indicators} indicators · {countries} countries.",
  "sources.scoped": "{country}: {units} admin-2 units in {areas} admin-1 areas.",
  "sources.scopedAgree": "Country totals match the sum of their records across all {n} indicators.",
  "sources.scopedDiffer": "Country totals do not match the sum of their records.",
  "sources.heading": "Sources",
  "sources.colSource": "Source",
  "sources.colProvides": "Provides",
  "sources.colAccess": "Access",
  "sources.colLicence": "Licence",
  "sources.colRetrieved": "Retrieved",
  "sources.selected": "Which records were selected",
  "sources.fields": "Where each number comes from",
  "sources.colShown": "Shown as",
  "sources.colField": "Field in the source",
  "sources.applied": "What was done to it",
  "sources.checks": "Cross-checks",
  "sources.checksNote": "Figures with two independent derivations, compared. These are computed when the data is built, not asserted here.",
  "sources.agrees": "agrees",
  "sources.differs": "differs",
  "sources.ofTotal": "{agree} of {total}",
  "sources.cite": "Cite this",
  "sources.copy": "Copy citation",
  "sources.copied": "Copied",
  "sources.untranslated": "Source descriptions, place names and database field names are shown in their original language.",

  "error.title": "Something went wrong",
  "error.body": "This page hit an error it could not recover from. Reloading usually clears it; if it happens every time, the message below is the useful part of a bug report.",
  "error.reload": "Reload the page",

  "lang.note": "Interface translated by machine, not reviewed by a speaker.",
} as const;

export type Key = keyof typeof en;
export type Table = Partial<Record<Key, string>>;

/* Fetch observations for the indicators listed in scripts/indicators.config.json and
   emit one data/indicators/<slug>.js per indicator.

   This script does NO indicator discovery. It only fetches observations for DCIDs that
   were already resolved with the un-datacommons MCP tools (search_indicators +
   get_variable_metadata) and recorded in the config. Never add a dcid here by hand.

   Usage: node scripts/fetch-indicator.mjs [slug ...]   (no args = all)
*/
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const cfg = JSON.parse(readFileSync(resolve(root, "scripts/indicators.config.json"), "utf8"));
const REST = cfg.rest;
const MIN_REPORTERS = cfg.minReportersPerYear ?? 30;
const MIN_COVERAGE = cfg.minYearCoverage ?? 0.5;   // share of the indicator's peak reporter count
const COUNTRIES = "Earth<-containedInPlace+{typeOf:Country}";

const warn = (...a) => console.error("  !", ...a);

/* Emit pure ASCII: these files are loaded as classic <script> and servers rarely
   set a charset on .js, so a raw UTF-8 name like "S\u00e3o Tom\u00e9" would mojibake.
   The original prototype's data file was escaped the same way. */
const ascii = (o) => JSON.stringify(o).replace(/[\u007f-\uffff]/g,
  (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));


async function observe(dcid, { expression, dcids }) {
  const u = new URL(REST + "/observation");
  u.searchParams.set("date", "");
  u.searchParams.append("variable.dcids", dcid);
  if (expression) u.searchParams.set("entity.expression", expression);
  if (dcids) u.searchParams.set("entity.dcids", dcids);
  for (const s of ["variable", "entity", "date", "value"]) u.searchParams.append("select", s);
  const r = await fetch(u);
  if (!r.ok) throw new Error(`${dcid}: HTTP ${r.status}`);
  const j = await r.json();
  return { byEntity: j.byVariable?.[dcid]?.byEntity ?? {}, facets: j.facets ?? {} };
}

/* entity map -> { ISO3: {year: value} }, taking the first (preferred) facet per entity */
function toSeries(byEntity, label) {
  const series = {};
  let facetId = null, multi = 0;
  for (const [entity, e] of Object.entries(byEntity)) {
    const m = /^country\/([A-Z]{3})$/.exec(entity);
    if (!m) continue;
    const facets = e.orderedFacets ?? [];
    if (!facets.length) continue;
    if (facets.length > 1) multi++;
    const f = facets[0];
    facetId ??= f.facetId;
    const byYear = {};
    for (const o of f.observations ?? []) if (o.value != null) byYear[String(o.date)] = o.value;
    if (Object.keys(byYear).length) series[m[1]] = byYear;
  }
  if (multi) warn(`${label}: ${multi} countries have >1 facet; used the preferred one — check for source mixing`);
  return { series, facetId };
}

/* years with enough reporting countries, asserted contiguous */
function yearDomain(series, label) {
  const count = {};
  for (const byYear of Object.values(series)) for (const y of Object.keys(byYear)) count[y] = (count[y] || 0) + 1;
  // A partial tail year (e.g. renewable-share 2024: 84 reporters against 225 in
  // 2023) would end the slider and the play animation on a mostly-empty map, so
  // require a share of the indicator's own peak coverage as well as a floor.
  const peak = Math.max(...Object.values(count));
  const floor = Math.max(MIN_REPORTERS, peak * MIN_COVERAGE);
  const kept = Object.keys(count).filter((y) => count[y] >= floor).map(Number).sort((a, b) => a - b);
  const dropped = Object.keys(count).map(Number).filter((y) => !kept.includes(y)).sort((a, b) => a - b);
  if (dropped.length) warn(`${label}: dropped thin years ${dropped.map((y) => `${y} (${count[y]}/${peak})`).join(", ")}`);
  if (!kept.length) throw new Error(`${label}: no year clears ${floor} reporters`);
  for (let i = 1; i < kept.length; i++) {
    if (kept[i] !== kept[i - 1] + 1) warn(`${label}: gap in year domain at ${kept[i - 1]}->${kept[i]}; clamping assumes contiguity`);
  }
  return kept.map(String);
}

const quantile = (sorted, p) => {
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
};

/* snap to 1 / 2 / 2.5 / 5 x 10^k so legend ticks read cleanly */
function nice(x) {
  if (!(x > 0)) return 0;
  const k = Math.pow(10, Math.floor(Math.log10(x))), n = x / k;
  const m = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return +(m * k).toPrecision(4);
}

function computeCuts(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const cuts = [];
  for (let i = 1; i <= 6; i++) {
    const c = nice(quantile(sorted, i / 7));
    if (!cuts.length || c > cuts[cuts.length - 1]) cuts.push(c);
  }
  // pad if snapping collapsed duplicates, so the ramp always has 6 breaks
  while (cuts.length < 6) cuts.push(nice((cuts[cuts.length - 1] || 1) * 2));
  return cuts;
}

async function build(ind) {
  console.error(`\n${ind.slug}  (${ind.dcid})`);

  const obs = await observe(ind.dcid, { expression: COUNTRIES });
  const { series, facetId } = toSeries(obs.byEntity, ind.slug);
  const provenanceUrl = obs.facets?.[facetId]?.provenanceUrl ?? null;
  console.error(`  ${Object.keys(series).length} countries`);

  const years = yearDomain(series, ind.slug);
  const yearSet = new Set(years);
  for (const byYear of Object.values(series)) for (const y of Object.keys(byYear)) if (!yearSet.has(y)) delete byYear[y];
  for (const [iso, byYear] of Object.entries(series)) if (!Object.keys(byYear).length) delete series[iso];
  console.error(`  years ${years[0]}-${years[years.length - 1]}`);

  // world reference: reported Earth series, else population-weighted, else median
  let world = {}, worldKind = "reported";
  const earth = await observe(ind.dcid, { dcids: "Earth" });
  const ef = earth.byEntity?.Earth?.orderedFacets?.[0];
  if (ef) {
    for (const o of ef.observations ?? []) if (o.value != null && yearSet.has(String(o.date))) world[String(o.date)] = o.value;
  }
  if (!Object.keys(world).length) {
    if (ind.aggregable === false) {
      worldKind = "median";
      warn("no Earth series and aggregable:false — using median");
    } else {
      worldKind = "popWeighted";
      warn("no Earth series — computing population-weighted world average");
      const pop = toSeries((await observe("Count_Person", { expression: COUNTRIES })).byEntity, "Count_Person").series;
      const totalPop = {};
      for (const byYear of Object.values(pop)) for (const [y, p] of Object.entries(byYear)) totalPop[y] = (totalPop[y] || 0) + p;
      for (const y of years) {
        let num = 0, den = 0;
        for (const [iso, byYear] of Object.entries(series)) {
          const v = byYear[y], p = pop[iso]?.[y];
          if (v != null && p != null) { num += v * p; den += p; }
        }
        // only trust a year that covers most of the world's people
        if (den && totalPop[y] && den / totalPop[y] >= 0.9) world[y] = +(num / den).toPrecision(6);
      }
      if (!Object.keys(world).length) { worldKind = "median"; warn("population coverage too thin — falling back to median"); }
    }
  }
  if (worldKind === "median") {
    for (const y of years) {
      const vs = Object.values(series).map((s) => s[y]).filter((v) => v != null).sort((a, b) => a - b);
      if (vs.length) world[y] = quantile(vs, 0.5);
    }
  }
  console.error(`  world: ${worldKind}, ${Object.keys(world).length} years`);

  const values = [];
  for (const byYear of Object.values(series)) for (const v of Object.values(byYear)) values.push(v);
  const sorted = [...values].sort((a, b) => a - b);
  const cuts = ind.cuts ?? computeCuts(values);
  if (ind.cuts) console.error(`  cuts: ${cuts.join(", ")} (pinned in config)`);
  else console.error(`  cuts: ${cuts.join(", ")} (quantile)`);

  const geo = JSON.parse(
    readFileSync(resolve(root, "data/world-geo.js"), "utf8").replace(/^[^{]*/, "").replace(/;\s*$/, "")
  );
  const missing = Object.keys(series).filter((iso) => !geo.names[iso]);
  if (missing.length) warn(`no display name for: ${missing.join(", ")} — resolve via MCP and add to world-geo.js`);

  const out = {
    slug: ind.slug, dcid: ind.dcid, variable: ind.variable,
    title: ind.title, eyebrow: ind.eyebrow, blurb: ind.blurb,
    panelTitle: ind.panelTitle, valueNoun: ind.valueNoun,
    unit: ind.unit, deltaNoun: ind.deltaNoun, direction: ind.direction,
    years, cuts,
    stats: { min: sorted[0], max: sorted[sorted.length - 1], p99: quantile(sorted, 0.99), n: sorted.length },
    series, world, worldKind,
    source: { ...ind.source, provenanceUrl, facetId },
    generatedAt: new Date().toISOString().slice(0, 10),
  };

  writeFileSync(
    resolve(root, `data/indicators/${ind.slug}.js`),
    "/* generated by scripts/fetch-indicator.mjs -- do not edit */\n" +
      `(window.UNDATA=window.UNDATA||{})[${JSON.stringify(ind.slug)}]=` + ascii(out) + ";\n"
  );
  console.error(`  -> data/indicators/${ind.slug}.js`);
}

const want = process.argv.slice(2);
for (const ind of cfg.indicators) {
  if (want.length && !want.includes(ind.slug)) continue;
  await build(ind);
}

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

/* entity map -> { ISO3: {year: value} }.
   Picks one facet per country. Some variables carry facets from different sources in
   DIFFERENT UNITS for different countries (Annual_Generation_Electricity lists an EIA
   GigawattHour facet first for the USA and a UNSD KilowattHour facet for everyone else),
   so `requireUnit` pins the unit and drops countries that have no facet in it. Without
   that the USA would land on the map a million-fold out, silently. */
function toSeries(byEntity, label, facets, { requireUnit = null, scale = 1 } = {}) {
  const series = {};
  let facetId = null, multi = 0, skipped = [], units = new Set();
  for (const [entity, e] of Object.entries(byEntity)) {
    const m = /^country\/([A-Z]{3})$/.exec(entity);
    if (!m) continue;
    const all = e.orderedFacets ?? [];
    if (!all.length) continue;
    const usable = requireUnit
      ? all.filter((f) => (facets?.[String(f.facetId)]?.unit ?? null) === requireUnit)
      : all;
    if (!usable.length) { skipped.push(m[1]); continue; }
    if (all.length > 1) multi++;
    const f = usable[0];
    facetId ??= f.facetId;
    units.add(facets?.[String(f.facetId)]?.unit ?? "?");
    const byYear = {};
    for (const o of f.observations ?? []) if (o.value != null) byYear[String(o.date)] = o.value * scale;
    if (Object.keys(byYear).length) series[m[1]] = byYear;
  }
  if (requireUnit && skipped.length)
    warn(`${label}: dropped ${skipped.length} countries with no ${requireUnit} facet: ${skipped.slice(0, 8).join(", ")}${skipped.length > 8 ? " ..." : ""}`);
  if (multi) warn(`${label}: ${multi} countries have >1 facet; took the ${requireUnit ? requireUnit + " one" : "preferred one — check for source mixing"}`);
  if (units.size > 1) warn(`${label}: MIXED UNITS across countries: ${[...units].join(", ")}`);
  return { series, facetId, unit: [...units][0] ?? null };
}

/* years with enough reporting countries, asserted contiguous */
function yearDomain(series, label, minCoverage) {
  const count = {};
  for (const byYear of Object.values(series)) for (const y of Object.keys(byYear)) count[y] = (count[y] || 0) + 1;
  // A partial tail year (e.g. renewable-share 2024: 84 reporters against 225 in
  // 2023) would end the slider and the play animation on a mostly-empty map, so
  // require a share of the indicator's own peak coverage as well as a floor.
  const peak = Math.max(...Object.values(count));
  const floor = Math.max(MIN_REPORTERS, peak * minCoverage);
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

  const opts = { requireUnit: ind.requireUnit ?? null, scale: ind.scale ?? 1 };
  const obs = await observe(ind.dcid, { expression: COUNTRIES });
  const { series, facetId, unit } = toSeries(obs.byEntity, ind.slug, obs.facets, opts);
  if (opts.scale !== 1) console.error(`  scaled by ${opts.scale} (${unit} -> ${ind.unit.symbol})`);
  const provenanceUrl = obs.facets?.[facetId]?.provenanceUrl ?? null;
  console.error(`  ${Object.keys(series).length} countries`);

  const years = yearDomain(series, ind.slug, ind.minYearCoverage ?? MIN_COVERAGE);
  const yearSet = new Set(years);
  for (const byYear of Object.values(series)) for (const y of Object.keys(byYear)) if (!yearSet.has(y)) delete byYear[y];
  for (const [iso, byYear] of Object.entries(series)) if (!Object.keys(byYear).length) delete series[iso];
  console.error(`  years ${years[0]}-${years[years.length - 1]}`);

  // world reference: reported Earth series, else population-weighted, else median
  let world = {}, worldKind = "reported";
  const earth = await observe(ind.dcid, { dcids: "Earth" });
  const eAll = earth.byEntity?.Earth?.orderedFacets ?? [];
  const ef = (opts.requireUnit
    ? eAll.filter((f) => (earth.facets?.[String(f.facetId)]?.unit ?? null) === opts.requireUnit)
    : eAll)[0];
  if (ef) {
    for (const o of ef.observations ?? [])
      if (o.value != null && yearSet.has(String(o.date))) world[String(o.date)] = o.value * opts.scale;
  }
  if (!Object.keys(world).length && ind.aggregate === "sum") {
    // An absolute total (TWh generated) aggregates by summing; averaging it would be meaningless.
    worldKind = "sum";
    warn("no Earth series — summing reporting countries");
    // Only publish a total for years whose reporting set accounts for nearly all of
    // world generation. Counting countries is the wrong test: most years miss only
    // tiny states, while a year missing China would read as generation halving. So
    // weigh each year's reporters by what they contributed in the best-covered year.
    // A thin year stays on the map; it just carries no world figure, and the
    // sparkline already breaks on nulls.
    const counts = years.map((y) => [y, Object.values(series).filter((b) => b[y] != null).length]);
    const ref = counts.reduce((a, b) => (b[1] > a[1] ? b : a))[0];
    const refTotal = Object.values(series).reduce((t, b) => t + (b[ref] ?? 0), 0);
    const thin = [];
    for (const y of years) {
      let t = 0, covered = 0, k = 0;
      for (const byYear of Object.values(series)) {
        if (byYear[y] == null) continue;
        t += byYear[y]; k++; covered += byYear[ref] ?? 0;
      }
      const share = refTotal ? covered / refTotal : 0;
      if (k && share >= 0.95) world[y] = +t.toPrecision(8);
      else if (k) thin.push(`${y} (${(share * 100).toFixed(0)}% of ${ref} output)`);
    }
    if (thin.length) warn(`no world total for years with thin output coverage: ${thin.join(", ")}`);
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
    sourceNote: ind.sourceNote ?? null,
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

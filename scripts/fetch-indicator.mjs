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

/* Snap to a round number so legend ticks read cleanly. The ladder has to be fine enough
   for narrow distributions: transmission losses sit mostly between 4% and 25%, and a
   coarse 1/2/2.5/5 ladder collapses four of the six quantiles onto the same value. */
const LADDER = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
function nice(x) {
  if (!(x > 0)) return 0;
  const k = Math.pow(10, Math.floor(Math.log10(x))), n = x / k;
  return +((LADDER.find((m) => n <= m) ?? 10) * k).toPrecision(4);
}

function computeCuts(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const max = sorted[sorted.length - 1];
  const raw = [];
  for (let i = 1; i <= 6; i++) raw.push(quantile(sorted, i / 7));

  // Prefer snapped cuts, but only if they stay strictly increasing and inside the data.
  const snapped = raw.map(nice);
  const usable = snapped.every((v, i) => v > 0 && (i === 0 || v > snapped[i - 1]) && v < max);
  if (usable) return snapped;

  // Otherwise keep the quantiles themselves, rounded just enough to stay distinct.
  // Padding past the last cut (the old fallback) invented breaks above the data's own
  // maximum, which put empty bins at the top of the ramp.
  const out = [];
  for (const q of raw) {
    let v = +q.toPrecision(2);
    while (out.length && v <= out[out.length - 1]) v = +(v + Math.max(0.1, v * 0.05)).toPrecision(3);
    out.push(v);
  }
  return out;
}

/* Build one series from several variables: numerator / sum(signed denominator terms).
   Transmission losses are only meaningful against total SUPPLY, not domestic generation —
   dividing by generation alone gives Jersey 92.6% and Andorra 59.5%, because they import
   most of their power. An optional term defaults to 0 only for countries that never report
   it at all (no trade record anywhere means an isolated grid); for a country that reports
   it in other years a missing year is a data GAP, and the country-year is dropped. Palestine
   and Djibouti both import most of their power and have gaps — reading those as zero trade
   put them above 100% loss. A missing required term always drops the country-year. Returns the component series too, so the world reference
   can be a ratio of totals rather than a mean of ratios. */
async function buildDerived(ind) {
  const opts = { requireUnit: ind.requireUnit ?? null, scale: 1 };
  const terms = [ind.derived.numerator, ...ind.derived.denominator];
  const loaded = {};
  let provenanceUrl = null, facetId = null;
  for (const t of terms) {
    if (loaded[t.dcid]) continue;
    const o = await observe(t.dcid, { expression: COUNTRIES });
    const r = toSeries(o.byEntity, `${ind.slug}:${t.dcid}`, o.facets, opts);
    loaded[t.dcid] = r.series;
    provenanceUrl ??= o.facets?.[r.facetId]?.provenanceUrl ?? null;
    facetId ??= r.facetId;
    console.error(`  ${t.dcid}: ${Object.keys(r.series).length} countries`);
  }

  const num = loaded[ind.derived.numerator.dcid];
  const mult = ind.derived.multiply ?? 1;
  // Which countries ever report each optional term, so a gap can be told from a true zero.
  // Treating every missing optional value as a gap drops ~1000 country-years, because
  // trade reporting simply thins out in older years. Only treat it as a gap where the term
  // is MATERIAL for that country: take the median share it contributes in the years it is
  // reported, and if that is small, assuming zero is harmless. Palestine and Djibouti import
  // nearly all their power, so their missing years are real gaps; a country with negligible
  // trade keeps its older years.
  const MATERIAL = 0.05;
  const required = ind.derived.denominator.filter((t) => !t.optional);
  const reports = {};
  for (const t of ind.derived.denominator) {
    if (!t.optional) continue;
    const material = new Set();
    for (const [iso, byYear] of Object.entries(loaded[t.dcid] ?? {})) {
      const shares = [];
      for (const [y, v] of Object.entries(byYear)) {
        let base = 0;
        for (const r of required) base += loaded[r.dcid]?.[iso]?.[y] ?? 0;
        if (base > 0) shares.push(Math.abs(v) / base);
      }
      if (shares.length) {
        shares.sort((a, b) => a - b);
        if (shares[Math.floor(shares.length / 2)] > MATERIAL) material.add(iso);
      }
    }
    reports[t.dcid] = material;
    console.error(`  ${t.dcid}: material for ${material.size} countries`);
  }
  const series = {}, parts = {};
  let skippedRequired = 0, nonPositive = 0, gaps = 0;
  const implausible = [];
  for (const [iso, byYear] of Object.entries(num)) {
    for (const [y, nv] of Object.entries(byYear)) {
      let den = 0, ok = true;
      let gap = false;
      for (const t of ind.derived.denominator) {
        const v = loaded[t.dcid]?.[iso]?.[y];
        if (v == null) {
          if (!t.optional) { ok = false; break; }
          if (reports[t.dcid]?.has(iso)) { gap = true; break; }  // material for this country: a gap, not a zero
          continue;
        }
        den += (t.sign ?? 1) * v;
      }
      if (!ok) { skippedRequired++; continue; }
      if (gap) { gaps++; continue; }
      if (!(den > 0)) { nonPositive++; continue; }
      const val = +((mult * nv) / den).toPrecision(6);
      // Backstop: a share of supply cannot exceed 100%, so anything above it is bad input.
      if (ind.plausibleMax != null && val > ind.plausibleMax) {
        implausible.push(`${iso} ${y} (${val.toFixed(0)})`); continue;
      }
      (series[iso] ??= {})[y] = val;
      (parts[iso] ??= {})[y] = { n: nv, d: den };
    }
  }
  if (skippedRequired) warn(`${ind.slug}: ${skippedRequired} country-years lack a required denominator term`);
  if (nonPositive) warn(`${ind.slug}: ${nonPositive} country-years had a non-positive denominator`);
  if (gaps) warn(`${ind.slug}: ${gaps} country-years dropped for a gap in an optional term the country reports elsewhere`);
  if (implausible.length) warn(`${ind.slug}: dropped ${implausible.length} over plausibleMax=${ind.plausibleMax}: ${implausible.join(", ")}`);
  return { series, parts, provenanceUrl, facetId };
}

async function build(ind) {
  console.error(`\n${ind.slug}  (${ind.dcid})`);

  const opts = { requireUnit: ind.requireUnit ?? null, scale: ind.scale ?? 1 };
  let series, parts = null, provenanceUrl, facetId;
  if (ind.derived) {
    ({ series, parts, provenanceUrl, facetId } = await buildDerived(ind));
  } else {
    const obs = await observe(ind.dcid, { expression: COUNTRIES });
    let unit;
    ({ series, facetId, unit } = toSeries(obs.byEntity, ind.slug, obs.facets, opts));
    if (opts.scale !== 1) console.error(`  scaled by ${opts.scale} (${unit} -> ${ind.unit.symbol})`);
    provenanceUrl = obs.facets?.[facetId]?.provenanceUrl ?? null;
  }
  console.error(`  ${Object.keys(series).length} countries`);

  const years = yearDomain(series, ind.slug, ind.minYearCoverage ?? MIN_COVERAGE);
  const yearSet = new Set(years);
  for (const byYear of Object.values(series)) for (const y of Object.keys(byYear)) if (!yearSet.has(y)) delete byYear[y];
  for (const [iso, byYear] of Object.entries(series)) if (!Object.keys(byYear).length) delete series[iso];
  console.error(`  years ${years[0]}-${years[years.length - 1]}`);

  // world reference: reported Earth series, else population-weighted, else median
  let world = {}, worldKind = "reported";
  if (ind.aggregate === "ratio") {
    // The world figure is total losses over total supply, not the mean of country
    // percentages — which would let a tiny grid weigh as much as India's. Gated the
    // same way a sum is: only for years whose reporters carry ~all of the denominator.
    worldKind = "ratio";
    const mult = ind.derived?.multiply ?? 1;
    const counts = years.map((y) => [y, Object.values(parts).filter((b) => b[y]).length]);
    const ref = counts.reduce((a, b) => (b[1] > a[1] ? b : a))[0];
    const refTotal = Object.values(parts).reduce((t, b) => t + (b[ref]?.d ?? 0), 0);
    // A ratio tolerates thinner coverage than a sum: a missing 10% of supply shifts an
    // average slightly, where it would cut a total by a tenth. So 90% here, 95% for sums.
    const need = ind.worldMinCoverage ?? 0.9;
    const thin = [];
    for (const y of years) {
      let n = 0, d = 0, covered = 0;
      for (const b of Object.values(parts)) {
        if (!b[y]) continue;
        n += b[y].n; d += b[y].d; covered += b[ref]?.d ?? 0;
      }
      const share = refTotal ? covered / refTotal : 0;
      if (d > 0 && share >= need) world[y] = +((mult * n) / d).toPrecision(6);
      else if (d > 0) thin.push(`${y} (${(share * 100).toFixed(0)}% of ${ref} supply)`);
    }
    if (thin.length) warn(`no world figure for years with thin coverage: ${thin.join(", ")}`);
  }

  const earth = ind.aggregate === "ratio" ? { byEntity: {}, facets: {} } : await observe(ind.dcid, { dcids: "Earth" });
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
    derivedFrom: ind.derived
      ? [ind.derived.numerator, ...ind.derived.denominator].map((t) => t.dcid)
      : null,
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

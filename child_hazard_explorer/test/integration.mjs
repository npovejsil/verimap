// Simulates exactly what the app does on load, against the shipped artifacts.
//
// The app is hazard-only and every byte it reads is static, so this needs no
// network: if these joins hold, the map paints.
import { readFileSync } from "node:fs";

const fail = (m) => { console.error("FAIL:", m); process.exitCode = 1; };
const read = (p) => JSON.parse(readFileSync(p, "utf8"));
const stemOf = (u) => u.replace(/_V\d+$/, "");

const places  = read("data/places.json");
const hazard  = read("data/hazard/countries.json");
const units   = read("data/hazard/units.json");
const index   = read("data/hazard/admin2-index.json");
const topo    = read("data/boundaries/adm0.min.topo.json");

console.log(`places : ${Object.keys(places.countries).length} countries`);
console.log(`hazard : ${Object.keys(hazard.countries).length} countries, ${hazard.indicators.length} indicators`);

// Every indicator must carry a unit, or the detail readout prints a bare number.
const missingUnits = hazard.indicators.filter((i) => !units[i]);
console.log(`units  : ${Object.keys(units).length} indicators`);
if (missingUnits.length) fail(`indicators without a unit: ${missingUnits.join(", ")}`);

// The world choropleth, built the way App does.
const INDICATOR = "PM25";
const values = new Map();
for (const [iso3, entry] of Object.entries(hazard.countries)) {
  const cell = entry.indicators[INDICATOR];
  if (cell && cell.pct !== null) values.set(iso3, cell.pct);
}
const geoms = topo.objects[Object.keys(topo.objects)[0]].geometries;
const isos = new Set(geoms.map((g) => g.properties?.iso3));
const painted = [...values.keys()].filter((k) => isos.has(k));
console.log(`choropleth: ${values.size} countries, join to boundaries ${painted.length}/${values.size}`);
if (painted.length / values.size < 0.9) fail("choropleth join below 90%");

// The drilldown, the way the app reaches it: a boundary chunk holds the
// country's two levels in one topology; the hazard chunk holds its records.
const bIndex = read("data/boundaries/country-index.json");
const bChunks = new Map();
const topoFor = (iso3) => {
  const n = bIndex[iso3];
  if (n === undefined) return null;
  if (!bChunks.has(n)) bChunks.set(n, read(`data/boundaries/country-${n}.json`));
  return bChunks.get(n)[iso3] ?? null;
};
const built = Object.keys(bIndex);
console.log(`boundaries built: ${built.length}/${Object.keys(index).length} countries`);

let checked = 0, joined = 0, geometry = 0;
for (const iso3 of built) {
  const chunk = index[iso3];
  if (chunk === undefined) { fail(`${iso3} has boundaries but no hazard records`); continue; }
  const detail = read(`data/hazard/admin2-${chunk}.json`)[iso3];
  if (!detail) { fail(`${iso3} missing from admin2-${chunk}.json`); continue; }
  const topo = topoFor(iso3);
  if (!topo?.objects?.adm2 || !topo?.objects?.adm1) { fail(`${iso3} is missing a level`); continue; }
  const stems = new Set(topo.objects.adm2.geometries.map((g) => g.properties?.stem));
  const wanted = [...new Set(detail.areas.map(stemOf))];
  checked++;
  joined += wanted.filter((s) => stems.has(s)).length;
  geometry += wanted.length;
}
const rate = geometry ? joined / geometry : 0;
console.log(`drilldown join: ${joined.toLocaleString()}/${geometry.toLocaleString()} units = ${(rate * 100).toFixed(3)}% across ${checked} countries`);
if (checked && rate < 0.99) fail("drilldown join below 99%");

// The detail readout for one unit: every field the panel prints must be there.
const KEN = read(`data/hazard/admin2-${index.KEN}.json`).KEN;
const block = KEN.indicators.RIVER_FLOOD;
const i = block.area.indexOf(KEN.areas.indexOf("KEN_0012_0003_V1"));
if (i < 0) fail("KEN_0012_0003_V1 has no RIVER_FLOOD record");
else {
  const facts = {
    exposed: block.exposed[i], pct: block.pct[i],
    hazard: block.hazard[i], cls: block.cls?.[i],
  };
  console.log(`KEN_0012_0003_V1 (Buret) river flood:`, JSON.stringify(facts), units.RIVER_FLOOD);
  for (const [k, v] of Object.entries(facts)) {
    if (v === undefined || v === null) fail(`Buret river flood ${k} is ${v}`);
  }
}

// The admin-1 level the app opens a country at. It is derived, not published,
// so check that it lines up with the records it came from.
const adm1 = read("data/hazard/adm1.json");
const kenTopo = topoFor("KEN");
const adm1Stems = new Set(kenTopo.objects.adm1.geometries.map((g) => g.properties?.stem));
console.log(`adm1 roll-up: ${Object.keys(adm1).length} countries, KEN ${adm1.KEN.areas.length} areas, ${adm1Stems.size} polygons`);
if (adm1.KEN.areas.length !== adm1Stems.size) fail("KEN admin-1 records and polygons disagree");
for (const a of adm1.KEN.areas) if (!adm1Stems.has(a)) fail(`${a} has no admin-1 polygon`);

// Buret's county must contain Buret's exposure.
const parent = new Map(
  kenTopo.objects.adm2.geometries.map((g) => [g.properties?.stem, g.properties?.adm1]),
);
const buretParent = parent.get("KEN_0012_0003");
console.log(`Buret's admin-1 parent: ${buretParent}`);
if (!buretParent) fail("Buret has no admin-1 parent");
else {
  const kids = KEN.indicators.RIVER_FLOOD;
  let sum = 0, pop = 0;
  kids.area.forEach((a, i) => {
    if (parent.get(stemOf(KEN.areas[a])) !== buretParent) return;
    sum += kids.exposed[i] ?? 0;
    pop += kids.pop?.[i] ?? 0;
  });
  const pb = adm1.KEN.indicators.RIVER_FLOOD;
  const j = pb.area.indexOf(adm1.KEN.areas.indexOf(buretParent));
  console.log(`  admin-2 children sum: exposed ${sum.toLocaleString()} of ${pop.toLocaleString()}`);
  console.log(`  admin-1 roll-up     : exposed ${pb.exposed[j].toLocaleString()} of ${pb.pop[j].toLocaleString()}, ${pb.pct[j]}%`);
  if (Math.abs(pb.exposed[j] - sum) > 1) fail("admin-1 exposure does not match its admin-2 records");
  if (Math.abs(pb.pop[j] - pop) > 1) fail("admin-1 population does not match its admin-2 records");
  const expect = pop ? (sum / pop) * 100 : null;
  if (expect !== null && Math.abs(pb.pct[j] - expect) > 0.02) fail("admin-1 percentage was not re-derived from totals");
}

console.log(process.exitCode ? "\nINTEGRATION FAILED" : "\nintegration OK");

// Edge cases for the choropleth class breaks. Run: node test/scale.mjs
const SEQUENTIAL = ["#cde2fb","#9ec5f4","#6da7ec","#3987e5","#256abf","#104281"];
function quantileBreaks(values, steps = SEQUENTIAL.length) {
  const sorted = values.filter(Number.isFinite).sort((a,b)=>a-b);
  if (!sorted.length) return [];
  const cut = (src) => {
    const out=[];
    for (let i=1;i<steps;i++) out.push(src[Math.floor((i/steps)*(src.length-1))]);
    return out.filter((b,i)=> i===0 || b>out[i-1]);
  };
  const breaks = cut(sorted);
  if (breaks.length >= steps-1) return breaks;
  const distinct=[...new Set(sorted)];
  if (distinct.length<=1) return breaks;
  const spread=cut(distinct);
  return spread.length>breaks.length?spread:breaks;
}
function colorFor(v,b){ if(!Number.isFinite(v))return"NO_DATA"; let i=0; while(i<b.length&&v>b[i])i++; return SEQUENTIAL[Math.min(i,SEQUENTIAL.length-1)];}
const cases={
 "uniform 0..100":Array.from({length:101},(_,i)=>i),
 "heavy skew":[...Array(90).fill(0.5),10,50,200,900,5000],
 "many zeroes":[...Array(60).fill(0),1,2,3,4,5,6,7,8,9,10],
 "all identical":Array(20).fill(7),
 "two values":[1,2],
};
let bad = 0;
const expected = { "uniform 0..100": 6, "heavy skew": 6, "many zeroes": 6, "all identical": 1, "two values": 2 };
for (const [n, v] of Object.entries(cases)) {
  const b = quantileBreaks(v);
  const s = {};
  for (const x of v) { const c = colorFor(x, b); s[c] = (s[c] || 0) + 1; }
  const used = Object.keys(s).length;
  const ok = used === expected[n];
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"} ${n.padEnd(16)} colours used=${used}/6 (expected ${expected[n]})  breaks=[${b.map(x => +x.toFixed(2)).join(", ")}]`);
}

// --- "No data" must be visibly distinct from everything around it -----------
// This is the check that was missing: the old no-data grey sat dE 3.7 from the
// map background, so 38 unpainted countries were effectively invisible. Values
// are read out of the real source, not copied here, so the test cannot pass
// against a palette the app no longer uses.
import { readFileSync } from "node:fs";

const scaleSrc = readFileSync(new URL("../src/scale.ts", import.meta.url), "utf8");
const mapSrc = readFileSync(new URL("../src/WorldMap.tsx", import.meta.url), "utf8");
const NO_DATA = scaleSrc.match(/export const NO_DATA = "(#[0-9a-fA-F]{6})"/)[1];
const RAMP = [...scaleSrc.match(/export const SEQUENTIAL = \[([^\]]+)\]/)[1]
  .matchAll(/#[0-9a-fA-F]{6}/g)].map((m) => m[0]);
const BG = mapSrc.match(/"background-color":\s*"(#[0-9a-fA-F]{6})"/)[1];

const oklab = (hex) => {
  const v = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  const [r, g, b] = v;
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s2 = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s2,
          1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s2,
          0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s2];
};
const dE = (a, b) => 100 * Math.hypot(...oklab(a).map((x, i) => x - oklab(b)[i]));

const MIN = 8;
const contrast = [
  ["no-data vs map background", dE(NO_DATA, BG)],
  ["no-data vs palest data step", dE(NO_DATA, RAMP[0])],
  ["no-data vs white borders", dE(NO_DATA, "#ffffff")],
];
console.log(`\nno-data separation (${NO_DATA}, target dE >= ${MIN})`);
for (const [name, d] of contrast) {
  const ok = d >= MIN;
  if (!ok) bad++;
  console.log(`  ${ok ? "PASS" : "FAIL"} ${name.padEnd(30)} dE ${d.toFixed(1)}`);
}

console.log(bad ? `\n${bad} failing` : "\nall scale cases pass");
process.exitCode = bad ? 1 : 0;

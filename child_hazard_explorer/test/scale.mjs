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
console.log(bad ? `\n${bad} failing` : "\nall scale cases pass");
process.exitCode = bad ? 1 : 0;

/** Sequential ramp for magnitude: one hue, light -> dark. Never a rainbow.
 *  Steps are UN-blue based and hold up against both light and dark surfaces. */
export const SEQUENTIAL = [
  "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#104281",
];

/** Categorical slots for trend lines. Verified with the palette validator in
 *  both modes: all checks pass. The light-mode contrast warning on slots 3-5
 *  is discharged by direct-labelling every line and offering a table view. */
export const CATEGORICAL_LIGHT = [
  "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
];
export const CATEGORICAL_DARK = [
  "#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300",
];

export function seriesColor(i: number, dark = false): string {
  const slots = dark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT;
  // Never cycle generated hues: past the last slot, callers fold into "Other".
  return slots[Math.min(i, slots.length - 1)];
}

/** Absent data, not a low value.
 *
 *  Kept neutral (chroma ~1.4) so it reads as "no reading exists" rather than as
 *  another step on the blue ramp, and deliberately strong: the previous value
 *  (#e6e6e2) sat OKLab dE 3.7 from the map background and 4.9 from the palest
 *  data step, which made 38 unpainted countries effectively invisible. White
 *  fails the same way (dE 4.1) because the background is near-white.
 *  This sits 27.7 from the background, 13.5 from the nearest data step and
 *  31.7 from the white borders -- while staying lighter than the dark end of
 *  the ramp, so absence never outranks the highest values. */
export const NO_DATA = "#9a9a90";
export const NO_DATA_DARK = "#383835";

/** Class breaks for the choropleth.
 *
 *  Plain quantiles are the right default -- most SDG indicators are skewed
 *  enough that equal-interval breaks wash the map into one colour. But when
 *  many places share a value (lots of zeroes, or a bounded index), the
 *  quantiles tie, the duplicates collapse, and you get the same washed-out map
 *  by a different route: a 95-value series with 90 ties yielded ONE break and
 *  left four of six colours unused.
 *
 *  So: quantiles over the raw values, and if ties have eaten the breaks, fall
 *  back to quantiles over the distinct values instead. */
export function quantileBreaks(values: number[], steps = SEQUENTIAL.length): number[] {
  const sorted = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (!sorted.length) return [];

  const cut = (source: number[]) => {
    const out: number[] = [];
    for (let i = 1; i < steps; i++) {
      out.push(source[Math.floor((i / steps) * (source.length - 1))]);
    }
    return out.filter((b, i) => i === 0 || b > out[i - 1]);
  };

  const breaks = cut(sorted);
  if (breaks.length >= steps - 1) return breaks;

  const distinct = [...new Set(sorted)];
  if (distinct.length <= 1) return breaks;
  const spread = cut(distinct);
  return spread.length > breaks.length ? spread : breaks;
}

export function colorFor(value: number | undefined, breaks: number[], dark = false): string {
  if (value === undefined || !Number.isFinite(value)) return dark ? NO_DATA_DARK : NO_DATA;
  let i = 0;
  while (i < breaks.length && value > breaks[i]) i++;
  return SEQUENTIAL[Math.min(i, SEQUENTIAL.length - 1)];
}

export function formatValue(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "--";
  const abs = Math.abs(v);
  if (abs >= 1e9) return (v / 1e9).toFixed(1) + "B";
  if (abs >= 1e6) return (v / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (v / 1e3).toFixed(1) + "k";
  if (abs >= 100) return v.toFixed(0);
  if (abs >= 1) return v.toFixed(1);
  return v.toFixed(2);
}

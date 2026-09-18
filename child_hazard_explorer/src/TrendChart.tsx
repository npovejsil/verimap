import { useMemo, useState } from "react";
import { seriesColor, formatValue } from "./scale";

export interface Series {
  key: string;
  label: string;
  points: { date: string; value: number }[];
}

interface Props {
  series: Series[];
  unit?: string;
}

const W = 640;
const H = 260;
const PAD = { top: 16, right: 116, bottom: 28, left: 46 };

/** Change over time. >= 2 series get a legend AND direct labels, so identity is
 *  never carried by colour alone. */
export default function TrendChart({ series, unit }: Props) {
  const [hoverYear, setHoverYear] = useState<number | null>(null);

  const model = useMemo(() => {
    const years: number[] = [];
    let lo = Infinity;
    let hi = -Infinity;
    for (const s of series) {
      for (const p of s.points) {
        const y = Number(p.date.slice(0, 4));
        if (Number.isFinite(y)) years.push(y);
        lo = Math.min(lo, p.value);
        hi = Math.max(hi, p.value);
      }
    }
    if (!years.length) return null;
    const x0 = Math.min(...years);
    const x1 = Math.max(...years);
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    return { x0, x1: x1 === x0 ? x0 + 1 : x1, lo: lo - pad, hi: hi + pad };
  }, [series]);

  if (!model) return <p className="empty">No time series for this selection.</p>;

  const sx = (year: number) =>
    PAD.left + ((year - model.x0) / (model.x1 - model.x0)) * (W - PAD.left - PAD.right);
  const sy = (v: number) =>
    H - PAD.bottom - ((v - model.lo) / (model.hi - model.lo)) * (H - PAD.top - PAD.bottom);

  const ticks = [model.lo, (model.lo + model.hi) / 2, model.hi];

  return (
    <div className="trend">
      <svg className="chart" width="100%" viewBox={`0 0 ${W} ${H}`} role="img">
        {/* Recessive gridlines, drawn behind the data. */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.left} x2={W - PAD.right} y1={sy(t)} y2={sy(t)} className="grid" />
            <text className="axis" x={PAD.left - 8} y={sy(t) + 4} textAnchor="end">
              {formatValue(t)}
            </text>
          </g>
        ))}
        <text className="axis" x={PAD.left} y={H - 8}>{model.x0}</text>
        <text className="axis" x={W - PAD.right} y={H - 8} textAnchor="end">{model.x1}</text>

        {series.slice(0, 6).map((s, i) => {
          const pts = [...s.points]
            .map((p) => ({ x: Number(p.date.slice(0, 4)), y: p.value }))
            .filter((p) => Number.isFinite(p.x))
            .sort((a, b) => a.x - b.x);
          if (!pts.length) return null;
          const d = pts.map((p, j) => `${j ? "L" : "M"}${sx(p.x)},${sy(p.y)}`).join(" ");
          const last = pts[pts.length - 1];
          return (
            <g key={s.key}>
              <path d={d} fill="none" stroke={seriesColor(i)} strokeWidth={2} />
              {pts.map((p) => (
                <circle
                  key={p.x}
                  cx={sx(p.x)}
                  cy={sy(p.y)}
                  r={hoverYear === p.x ? 5 : 3.5}
                  fill={seriesColor(i)}
                  stroke="#fcfcfb"
                  strokeWidth={2}
                  onMouseEnter={() => setHoverYear(p.x)}
                  onMouseLeave={() => setHoverYear(null)}
                />
              ))}
              {/* Direct label at the series end. */}
              <text className="series-label" x={sx(last.x) + 8} y={sy(last.y) + 4}>
                {s.label.length > 14 ? s.label.slice(0, 13) + "…" : s.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="legend">
        {series.slice(0, 6).map((s, i) => (
          <span key={s.key} className="legend-item">
            <i style={{ background: seriesColor(i) }} />
            {s.label}
          </span>
        ))}
        {unit && <span className="unit">Unit: {unit}</span>}
      </div>
    </div>
  );
}

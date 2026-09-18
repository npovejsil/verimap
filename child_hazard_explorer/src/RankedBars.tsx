import { useState } from "react";
import { SEQUENTIAL, formatValue } from "./scale";

export interface Row {
  key: string;
  label: string;
  value: number;
}

interface Props {
  rows: Row[];
  unit?: string;
  /** Places the user picked, drawn with an outline ring so they stand out. */
  highlight?: Set<string>;
  /** Makes the rows pickable. Used by the admin-2 drilldown, where clicking a
   *  bar puts that unit on the map. */
  onSelect?: (key: string) => void;
}

const BAR_H = 20;
const GAP = 6;
const LABEL_W = 148;
const VALUE_W = 68;

/** Ranked horizontal bars: the form for comparing magnitude across places.
 *  One series, so no legend -- the title names it -- and every bar is direct
 *  labelled rather than carrying a value axis. */
export default function RankedBars({ rows, unit, highlight, onSelect }: Props) {
  const [hover, setHover] = useState<string | null>(null);
  if (!rows.length) return <p className="empty">No values for this selection.</p>;

  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const max = Math.max(...sorted.map((r) => Math.abs(r.value)), 0) || 1;
  const height = sorted.length * (BAR_H + GAP);
  const plotW = 420;

  return (
    <svg
      className="chart"
      width="100%"
      height={height}
      viewBox={`0 0 ${LABEL_W + plotW + VALUE_W} ${height}`}
      role="img"
    >
      {sorted.map((row, i) => {
        const y = i * (BAR_H + GAP);
        const w = Math.max((Math.abs(row.value) / max) * plotW, 2);
        const on = hover === row.key;
        return (
          <g
            key={row.key}
            onMouseEnter={() => setHover(row.key)}
            onMouseLeave={() => setHover(null)}
            onClick={onSelect ? () => onSelect(row.key) : undefined}
            style={onSelect ? { cursor: "pointer" } : undefined}
          >
            {/* Full-row hit target, larger than the mark itself. */}
            <rect x={0} y={y} width={LABEL_W + plotW + VALUE_W} height={BAR_H + GAP} fill="transparent" />
            <text className="bar-label" x={LABEL_W - 8} y={y + BAR_H * 0.72} textAnchor="end">
              {row.label}
            </text>
            <rect
              x={LABEL_W}
              y={y}
              width={w}
              height={BAR_H}
              rx={4}
              fill={SEQUENTIAL[3]}
              opacity={on ? 1 : 0.92}
              stroke={highlight?.has(row.key) ? "#0b0b0b" : "none"}
              strokeWidth={highlight?.has(row.key) ? 1.5 : 0}
            />
            <text className="bar-value" x={LABEL_W + w + 8} y={y + BAR_H * 0.72}>
              {formatValue(row.value)}
              {unit ? ` ${unit}` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

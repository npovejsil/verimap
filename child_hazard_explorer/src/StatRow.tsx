export interface Stat {
  label: string;
  value: string;
  /** Rendered small after the value -- a unit, not part of the number. */
  suffix?: string;
}

/** A row of bare stat tiles.
 *
 *  The right form for a handful of numbers about one thing: children exposed,
 *  a share, a hazard measure and a class have no common scale, so four bars
 *  would invite a comparison that means nothing. No hover layer -- there is no
 *  mark to hover -- and the numbers wear text tokens rather than a series
 *  colour, so nothing here reads as an encoding. */
export default function StatRow({ stats }: { stats: Stat[] }) {
  return (
    <dl className="stats">
      {stats.map((stat) => (
        <div className="stat" key={stat.label}>
          <dt>{stat.label}</dt>
          <dd>
            {stat.value}
            {stat.suffix && <span className="stat-unit">{stat.suffix}</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

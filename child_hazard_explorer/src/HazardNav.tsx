import { HAZARD_LABELS, HAZARD_METRICS } from "./data/hazard";
import { useStore } from "./store";

/** The 22 hazard indicators. Unlike the SDG tree this is a flat list -- the
 *  database has one level, a single year (2025), and children 0-17 only. */
export default function HazardNav({ indicators }: { indicators: string[] }) {
  const active = useStore((s) => s.hazardIndicator);
  const setHazard = useStore((s) => s.setHazard);
  const metric = useStore((s) => s.hazardMetric);
  const setMetric = useStore((s) => s.setHazardMetric);

  return (
    <div className="hazard-nav">
      <div className="metric-switch">
        {HAZARD_METRICS.map((m) => (
          <button
            key={m.key}
            className={`pill ${metric === m.key ? "on" : ""}`}
            onClick={() => setMetric(m.key)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <p className="note">
        Children aged 0&ndash;17 &middot; 2025 &middot; aggregated from 41,023 admin-2 units
      </p>
      {indicators.map((code) => (
        <button
          key={code}
          className={`variable ${active === code ? "active" : ""}`}
          onClick={() => setHazard(code)}
          title={code}
        >
          {HAZARD_LABELS[code] ?? code}
        </button>
      ))}
    </div>
  );
}

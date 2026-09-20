import { useEffect, useState } from "react";
import { HAZARD_METRICS } from "./data/hazard";
import { loadProvenance } from "./data/provenance";
import { useStore } from "./store";
import { useT } from "./i18n";
import { indicatorLabel } from "./i18n/indicators";

/** The 22 hazard indicators. Unlike the SDG tree this is a flat list -- the
 *  database has one level, a single year (2025), and children 0-17 only. */
export default function HazardNav({ indicators }: { indicators: string[] }) {
  const active = useStore((s) => s.hazardIndicator);
  const setHazard = useStore((s) => s.setHazard);
  const metric = useStore((s) => s.hazardMetric);
  const setMetric = useStore((s) => s.setHazardMetric);
  // Counted from the shipped data rather than written here: this line used to
  // claim 41,023 units while the data carried 40,641.
  const [units, setUnits] = useState<number | null>(null);
  const { t, n, locale } = useT();
  useEffect(() => {
    loadProvenance().then((p) => setUnits(p?.counts.admin2_units ?? null));
  }, []);

  return (
    <div className="hazard-nav">
      <div className="metric-switch">
        {HAZARD_METRICS.map((m) => (
          <button
            key={m.key}
            className={`pill ${metric === m.key ? "on" : ""}`}
            onClick={() => setMetric(m.key)}
          >
            {t(m.key === "pct" ? "metric.pct" : "metric.exposed")}
          </button>
        ))}
      </div>
      <p className="note">
        {t("app.subtitle")}
        {units !== null && <> &middot; {n(units)}</>}
      </p>
      {indicators.map((code) => (
        <button
          key={code}
          className={`variable ${active === code ? "active" : ""}`}
          onClick={() => setHazard(code)}
          title={code}
        >
          {indicatorLabel(code, locale)}
        </button>
      ))}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import HazardNav from "./HazardNav";
import HazardAreas from "./HazardAreas";
import StatRow, { type Stat } from "./StatRow";
import WorldMap, { type AreaLayer, type AreaStatus } from "./WorldMap";
import RankedBars, { type Row } from "./RankedBars";
import {
  HAZARD_LABELS,
  HAZARD_MEASURE,
  HAZARD_METRICS,
  areaFacts,
  areaValues,
  loadHazard,
  loadUnits,
  type HazardCountries,
} from "./data/hazard";
import { useHazardDetail } from "./useHazardDetail";
import { useStore, type Places } from "./store";
import { SEQUENTIAL, formatValue, quantileBreaks } from "./scale";

/** Hazard measures are small numbers where the second decimal carries meaning
 *  (0.84 m of flood, 28.03 µg/m³), so they don't go through the choropleth's
 *  compact formatter. */
const measure = (v: number) =>
  Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(2);

export default function App() {
  const {
    places, selected, hazardIndicator, hazardMetric, selectedArea,
    adminLevel, adminLevelAuto,
    setPlaces, clearSelection, togglePlace, setSelectedArea, setAdminLevel,
  } = useStore();

  const [hazard, setHazard] = useState<HazardCountries | null>(null);
  const [units, setUnits] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [areaStatus, setAreaStatus] = useState<AreaStatus>("off");

  useEffect(() => {
    fetch("places.json")
      .then((r) => r.json() as Promise<Places>)
      .then(setPlaces)
      .catch((e: unknown) => setError(String(e)));
    loadHazard().then(setHazard).catch((e: unknown) => setError(String(e)));
    loadUnits().then(setUnits);
  }, [setPlaces]);

  /** One value per country, for the world choropleth. */
  const countryValues = useMemo(() => {
    const m = new Map<string, number>();
    if (!hazard) return m;
    for (const [iso3, entry] of Object.entries(hazard.countries)) {
      const cell = entry.indicators[hazardIndicator];
      if (!cell) continue;
      const value = hazardMetric === "pct" ? cell.pct : cell.exposed;
      if (value !== null && Number.isFinite(value)) m.set(iso3, value);
    }
    return m;
  }, [hazard, hazardIndicator, hazardMetric]);

  // --- Admin-2 drilldown ---------------------------------------------------
  // The country numbers are roll-ups of admin-2 units, so selecting a single
  // country drops the map to the level the data actually lives at.
  const drilldownIso = useMemo(() => {
    const countries = selected.filter((d) => d.startsWith("country/"));
    return countries.length === 1 ? countries[0].slice(8) : null;
  }, [selected]);

  const { detail: areaDetail, nameFor } = useHazardDetail(drilldownIso, adminLevel);

  const areaVals = useMemo(
    () =>
      areaDetail
        ? areaValues(areaDetail, hazardIndicator, hazardMetric)
        : new Map<string, number>(),
    [areaDetail, hazardIndicator, hazardMetric],
  );

  const areaBreaks = useMemo(
    () => quantileBreaks([...new Set(areaVals.values())]),
    [areaVals],
  );

  const hazardUnit = HAZARD_METRICS.find((m) => m.key === hazardMetric)?.unit;

  const areaLayer: AreaLayer | null = useMemo(() => {
    if (!drilldownIso || areaVals.size === 0) return null;
    return {
      iso3: drilldownIso,
      level: adminLevel,
      nameFor,
      values: areaVals,
      breaks: areaBreaks,
      unit: hazardUnit,
      focus: selectedArea,
      onSelect: (stem) => setSelectedArea(stem === selectedArea ? null : stem),
    };
  }, [drilldownIso, adminLevel, nameFor, areaVals, areaBreaks, hazardUnit, selectedArea, setSelectedArea]);

  /** Every number the database holds for the clicked unit. */
  const facts = useMemo(
    () =>
      areaDetail && selectedArea
        ? areaFacts(areaDetail, hazardIndicator, selectedArea)
        : null,
    [areaDetail, selectedArea, hazardIndicator],
  );

  const areaStats: Stat[] = facts
    ? [
        {
          label: "Exposed children",
          value: facts.exposed === null ? "—" : Math.round(facts.exposed).toLocaleString(),
        },
        {
          label: "Exposure",
          value: facts.pct === null ? "—" : facts.pct.toFixed(1),
          suffix: facts.pct === null ? undefined : "%",
        },
        {
          label: "Children in area",
          value: facts.pop === null ? "—" : Math.round(facts.pop).toLocaleString(),
        },
        {
          label: HAZARD_MEASURE[hazardIndicator] ?? "Hazard (mean)",
          value: facts.hazard === null ? "—" : measure(facts.hazard),
          suffix: facts.hazard === null ? undefined : units[hazardIndicator],
        },
        {
          label: "Exposure class",
          value: facts.cls === null ? "—" : facts.cls.toFixed(1),
        },
      ]
    : [];

  const unit = hazardUnit;
  const title = `${HAZARD_LABELS[hazardIndicator] ?? hazardIndicator} — ${
    HAZARD_METRICS.find((m) => m.key === hazardMetric)?.label
  }`;

  const nameOfCountry = (dcid: string) => places?.countries[dcid]?.name ?? dcid;

  const selectedIsos = useMemo(
    () => selected.filter((d) => d.startsWith("country/")).map((d) => d.slice(8)),
    [selected],
  );

  // Zoom to the country on selection. The drilldown layer no longer fits the
  // view itself: one country's admin-2 extent is its country extent, and two
  // fits would fight over the same move.
  const focusIsos = useMemo(
    () => (drilldownIso ? [drilldownIso] : null),
    [drilldownIso],
  );

  const rows: Row[] = useMemo(
    () =>
      selected
        .map((d) => ({
          key: d,
          label: nameOfCountry(d),
          value: countryValues.get(d.slice(8)) ?? NaN,
        }))
        .filter((r) => Number.isFinite(r.value)),
    [selected, countryValues, places],
  );

  const breaks = useMemo(
    () => quantileBreaks([...new Set(countryValues.values())]),
    [countryValues],
  );
  const painted = countryValues.size;
  const drilling = areaStatus === "ok" && !!areaLayer;

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <h1>Child Hazard Explorer</h1>
          <p className="sub">
            UNICEF Global Child Hazard Database · children 0–17 · 2025
          </p>
        </div>

        <div className="controls">
          <div className="control grow">
            <span className="control-label">Selection</span>
            <div className="pills">
              {selected.length === 0 ? (
                <span className="hint">
                  Click a country to open its admin-2 units, then click a unit for detail.
                </span>
              ) : (
                <>
                  {selected.map((d) => (
                    <button key={d} className="pill on" onClick={() => togglePlace(d)}>
                      {nameOfCountry(d)} ✕
                    </button>
                  ))}
                  <button className="pill clear" onClick={clearSelection}>
                    Clear ({selected.length})
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      <aside className="sidebar">
        <HazardNav indicators={hazard?.indicators ?? []} />
      </aside>

      <main className="main">
        <div className="panel map-panel">
          <div className="panel-head">
            <h2>{title}</h2>
            {drilldownIso && (
              <div className="seg">
                <button
                  className={adminLevel === 1 ? "on" : ""}
                  onClick={() => setAdminLevel(1, true)}
                >
                  Admin 1
                </button>
                <button
                  className={adminLevel === 2 ? "on" : ""}
                  onClick={() => setAdminLevel(2, true)}
                >
                  Admin 2
                </button>
              </div>
            )}
            {!hazard && !error && <span className="badge">Loading…</span>}
            {error && <span className="badge err">{error}</span>}
          </div>
          <WorldMap
            values={countryValues}
            unit={unit}
            selectedIsos={selectedIsos}
            onSelect={(iso3) => togglePlace(`country/${iso3}`)}
            focusIsos={focusIsos}
            areas={areaLayer}
            onAreaStatus={setAreaStatus}
            onLevelHint={(level) => adminLevelAuto && setAdminLevel(level)}
          />
          <div className="legend-row">
            <span className="legend-title">
              {unit ? `Latest value (${unit})` : "Latest value"}
            </span>
            <div className="ramp">
              {SEQUENTIAL.map((c, i) => {
                const b = drilling ? areaBreaks[i] : breaks[i];
                return (
                  <span key={c} className="swatch" style={{ background: c }}>
                    <em>{b !== undefined ? formatValue(b) : ""}</em>
                  </span>
                );
              })}
            </div>
            <span className="legend-note">
              {drilling
                ? `${areaVals.size} admin-${adminLevel} areas in ${drilldownIso} · click one for detail`
                : `${painted} countries · click one to zoom in`}
            </span>
          </div>
          {areaStatus === "missing" && drilldownIso && (
            <p className="note">
              No boundaries for {drilldownIso} yet — the map is showing the country
              outline only. Build them with{" "}
              <code>python3 etl/build_adm2.py {drilldownIso}</code>.
            </p>
          )}
          <p className="prov">
            Source: UNICEF Global Child Hazard Database · children 0–17, 2025 ·
            boundaries UNICEF GeoRepo (CC BY 4.0)
          </p>
        </div>

        {selectedArea && (
          <div className="panel">
            <div className="panel-head">
              <h2>{nameFor(selectedArea)}</h2>
              <button className="linkish" onClick={() => setSelectedArea(null)}>
                Clear
              </button>
            </div>
            {facts ? (
              <>
                <p className="note">
                  {facts.ucode} · {HAZARD_LABELS[hazardIndicator] ?? hazardIndicator} ·{" "}
                  {adminLevel === 1 ? (
                    // Admin-1 has no rows in the database; say so, and say how
                    // much of the parent the number actually covers.
                    <>
                      calculated from {facts.units ?? "?"} of {facts.total ?? "?"} admin-2
                      units
                      {facts.units !== undefined &&
                        facts.total !== undefined &&
                        facts.units < facts.total &&
                        " — the rest have no record for this indicator"}
                    </>
                  ) : (
                    "as recorded in the database"
                  )}
                </p>
                <StatRow stats={areaStats} />
              </>
            ) : (
              <p className="empty">
                No {HAZARD_LABELS[hazardIndicator] ?? hazardIndicator} record for this unit.
              </p>
            )}
          </div>
        )}

        {drilldownIso && (
          <div className="panel">
            <div className="panel-head">
              <h2>Subnational detail</h2>
              <span className="hint">
                {adminLevel === 1
                  ? "Admin-1 areas, rolled up from the admin-2 records"
                  : "Admin-2 units, as the database holds them"}
              </span>
            </div>
            <HazardAreas iso3={drilldownIso} level={adminLevel} />
          </div>
        )}

        {selected.length > 1 && (
          <div className="panel">
            <div className="panel-head">
              <h2>Countries compared</h2>
              <button className="linkish" onClick={() => setShowTable(!showTable)}>
                {showTable ? "Show chart" : "Show table"}
              </button>
            </div>
            {showTable ? (
              <table className="table">
                <thead>
                  <tr><th>Country</th><th>Value</th><th>Year</th></tr>
                </thead>
                <tbody>
                  {[...rows].sort((a, b) => b.value - a.value).map((r) => (
                    <tr key={r.key}>
                      <td>{r.label}</td>
                      <td>{formatValue(r.value)}{unit ? ` ${unit}` : ""}</td>
                      <td>2025</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <RankedBars rows={rows} unit={unit} highlight={new Set(selected)} />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

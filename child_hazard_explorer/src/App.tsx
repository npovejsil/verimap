import { useEffect, useMemo, useState } from "react";
import HazardNav from "./HazardNav";
import HazardAreas from "./HazardAreas";
import StatRow, { type Stat } from "./StatRow";
import WorldMap, { type AreaLayer, type AreaStatus } from "./WorldMap";
import RankedBars, { type Row } from "./RankedBars";
import {
  HAZARD_METRICS,
  areaFacts,
  areaValues,
  loadHazard,
  loadUnits,
  type HazardCountries,
} from "./data/hazard";
import SourcePanel from "./SourcePanel";
import { fieldFor, loadProvenance, type Provenance } from "./data/provenance";
import { useHazardDetail } from "./useHazardDetail";
import { useStore, type Places } from "./store";
import { LANGUAGES, useT } from "./i18n";
import { indicatorLabel, measureLabel } from "./i18n/indicators";
import { NO_DATA, SEQUENTIAL, formatValue, quantileBreaks } from "./scale";

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
    locale, setLocale,
  } = useStore();
  const { t, n, rtl } = useT();

  const [hazard, setHazard] = useState<HazardCountries | null>(null);
  const [units, setUnits] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [areaStatus, setAreaStatus] = useState<AreaStatus>("off");
  const [prov, setProv] = useState<Provenance | null>(null);
  // Without a map there is no other way to pick a country, so the header grows
  // a plain selector instead.
  const [noMap, setNoMap] = useState(false);
  /** Counted from what the map actually paints, per layer. */
  const [blank, setBlank] = useState<{ world: number; area: number }>({ world: 0, area: 0 });

  useEffect(() => {
    fetch("places.json")
      .then((r) => r.json() as Promise<Places>)
      .then(setPlaces)
      .catch((e: unknown) => setError(String(e)));
    loadHazard().then(setHazard).catch((e: unknown) => setError(String(e)));
    loadUnits().then(setUnits);
    loadProvenance().then(setProv);
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

  /** Admin-2 is recorded, so it names its source field; admin-1 is computed,
   *  so it names the derivation rather than a field that has no value there. */
  const trace = (shown: string, derived: string) =>
    adminLevel === 2 ? fieldFor(prov, shown) : derived;

  const areaStats: Stat[] = facts
    ? [
        {
          label: t("stat.exposed"),
          value: facts.exposed === null ? "—" : Math.round(facts.exposed).toLocaleString(),
          source: trace("Exposed children", "sum of children"),
        },
        {
          label: t("stat.exposure"),
          value: facts.pct === null ? "—" : facts.pct.toFixed(1),
          suffix: facts.pct === null ? undefined : "%",
          source: trace("Exposure %", "re-derived from totals"),
        },
        {
          label: t("stat.population"),
          value: facts.pop === null ? "—" : Math.round(facts.pop).toLocaleString(),
          source: trace("Children in area", "sum of children"),
        },
        {
          label: measureLabel(hazardIndicator, t("stat.hazard")),
          value: facts.hazard === null ? "—" : measure(facts.hazard),
          suffix: facts.hazard === null ? undefined : units[hazardIndicator],
          source: trace("Hazard measure", "mean of children"),
        },
        {
          label: t("stat.class"),
          value: facts.cls === null ? "—" : facts.cls.toFixed(1),
          source: trace("Exposure class", "max of children"),
        },
      ]
    : [];

  const unit = hazardUnit;
  const title = `${indicatorLabel(hazardIndicator, locale)} — ${t(
    hazardMetric === "pct" ? "metric.pct" : "metric.exposed",
  )}`;

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
  const missing = drilling ? blank.area : blank.world;

  return (
    <div className="app" dir={rtl ? "rtl" : "ltr"}>
      <header className="header">
        <div className="brand">
          <h1>{t("app.title")}</h1>
          <p className="sub">{t("app.subtitle")}</p>
        </div>

        <div className="controls">

          <div className="control grow">
            <span className="control-label">{t("header.selection")}</span>
            <div className="pills">
              {noMap && places && (
                <select
                  className="country-select"
                  value=""
                  onChange={(e) => e.target.value && togglePlace(e.target.value)}
                  aria-label={t("header.chooseCountry")}
                >
                  <option value="">{t("header.chooseCountry")}</option>
                  {Object.entries(places.countries)
                    .filter(([dcid]) => !selected.includes(dcid))
                    .sort((a, b) => a[1].name.localeCompare(b[1].name))
                    .map(([dcid, info]) => (
                      <option key={dcid} value={dcid}>{info.name}</option>
                    ))}
                </select>
              )}
              {selected.length === 0 ? (
                <span className="hint">
                  {t(noMap ? "header.hintNoMap" : "header.hint")}
                </span>
              ) : (
                <>
                  {selected.map((d) => (
                    <button key={d} className="pill on" onClick={() => togglePlace(d)}>
                      {nameOfCountry(d)} ✕
                    </button>
                  ))}
                  <button className="pill clear" onClick={clearSelection}>
                    {t("header.clear", { count: selected.length })}
                  </button>
                </>
              )}
            </div>
          </div>

          <div className="control lang">
            <span className="control-label">{t("header.language")}</span>
            <select
              className="country-select"
              value={locale}
              onChange={(e) => setLocale(e.target.value as typeof locale)}
              aria-label={t("header.language")}
              title={t("lang.note")}
            >
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
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
                  {t("level.admin1")}
                </button>
                <button
                  className={adminLevel === 2 ? "on" : ""}
                  onClick={() => setAdminLevel(2, true)}
                >
                  {t("level.admin2")}
                </button>
              </div>
            )}
            {!hazard && !error && <span className="badge">{t("map.loading")}</span>}
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
            onUnsupported={() => setNoMap(true)}
            onCoverage={(scope, noData) =>
              setBlank((b) => (b[scope] === noData ? b : { ...b, [scope]: noData }))
            }
          />
          <div className="legend-row">
            <span className="legend-title">
              {unit ? t("map.legendTitleUnit", { unit }) : t("map.legendTitle")}
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
            {missing > 0 && (
              <span className="legend-missing">
                <i style={{ background: NO_DATA }} />
                {t("map.noData", { count: n(missing) })}
              </span>
            )}
            <span className="legend-note">
              {drilling
                ? t("map.areas", { count: n(areaVals.size), level: adminLevel, iso3: drilldownIso ?? "" })
                : t("map.countries", { count: n(painted) })}
            </span>
          </div>
          {areaStatus === "missing" && drilldownIso && (
            <p className="note">
              {t("map.noBoundaries", { iso3: drilldownIso ?? "" })}{" "}
              <code>python3 etl/build_adm2.py {drilldownIso}</code>
            </p>
          )}
          <p className="prov">
            {t("map.source")}
          </p>
        </div>

        {selectedArea && (
          <div className="panel">
            <div className="panel-head">
              <h2>{nameFor(selectedArea)}</h2>
              <button className="linkish" onClick={() => setSelectedArea(null)}>
                {t("panel.clear")}
              </button>
            </div>
            {facts ? (
              <>
                <p className="note">
                  {facts.ucode} · {indicatorLabel(hazardIndicator, locale)} ·{" "}
                  {adminLevel === 1 ? (
                    // Admin-1 has no rows in the database; say so, and say how
                    // much of the parent the number actually covers.
                    <>
                      {t("readout.calculated", {
                        units: facts.units ?? "?",
                        total: facts.total ?? "?",
                      })}
                      {facts.units !== undefined &&
                        facts.total !== undefined &&
                        facts.units < facts.total &&
                        t("readout.calculatedRest")}
                    </>
                  ) : (
                    t("readout.recorded")
                  )}
                </p>
                <StatRow stats={areaStats} />
              </>
            ) : (
              <p className="empty">
                {t("readout.noRecord", { indicator: indicatorLabel(hazardIndicator, locale) })}
              </p>
            )}
          </div>
        )}

        {drilldownIso && (
          <div className="panel">
            <div className="panel-head">
              <h2>{t("panel.subnational")}</h2>
              <span className="hint">
                {t(adminLevel === 1 ? "panel.subnationalAdm1" : "panel.subnationalAdm2")}
              </span>
            </div>
            <HazardAreas iso3={drilldownIso} level={adminLevel} />
          </div>
        )}

        {selected.length > 1 && (
          <div className="panel">
            <div className="panel-head">
              <h2>{t("panel.compared")}</h2>
              <button className="linkish" onClick={() => setShowTable(!showTable)}>
                {t(showTable ? "panel.showChart" : "panel.showTable")}
              </button>
            </div>
            {showTable ? (
              <table className="table">
                <thead>
                  <tr><th>{t("panel.country")}</th><th>{t("panel.value")}</th><th>{t("panel.year")}</th></tr>
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

        {/* Reference material: last, after everything it describes. */}
        <SourcePanel
          prov={prov}
          iso3={drilldownIso}
          countryName={drilldownIso ? nameOfCountry(`country/${drilldownIso}`) : undefined}
        />
      </main>
    </div>
  );
}

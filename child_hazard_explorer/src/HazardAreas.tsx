import RankedBars, { type Row } from "./RankedBars";
import { HAZARD_LABELS, stemOf, type AdminLevel } from "./data/hazard";
import { useHazardDetail } from "./useHazardDetail";
import { useStore } from "./store";
import { useT } from "./i18n";

const TOP_N = 15;

/** Subnational detail for a single selected country. The hazard database is
 *  admin-2 throughout -- the country numbers elsewhere in this app are roll-ups
 *  of these units, so this is where the data actually lives.
 *
 *  Rows are keyed by versionless stem, the same key the map layer paints, so
 *  clicking a bar highlights that unit on the map and vice versa. */
export default function HazardAreas({
  iso3,
  level = 2,
}: {
  iso3: string;
  level?: AdminLevel;
}) {
  const indicator = useStore((s) => s.hazardIndicator);
  const metric = useStore((s) => s.hazardMetric);
  const selectedArea = useStore((s) => s.selectedArea);
  const setSelectedArea = useStore((s) => s.setSelectedArea);
  const { detail, loading, nameFor } = useHazardDetail(iso3, level);
  const { t } = useT();

  if (loading) return <p className="empty">{t("bars.loading", { level })}</p>;
  if (!detail) return <p className="empty">{t("bars.noCountry", { iso3 })}</p>;

  const block = detail.indicators[indicator];
  if (!block) {
    return (
      <p className="empty">
        {t("bars.noIndicator", { indicator: HAZARD_LABELS[indicator] ?? indicator, iso3 })}
      </p>
    );
  }

  const source = metric === "pct" ? block.pct : block.exposed;
  const all: Row[] = block.area
    .map((areaIndex, i) => {
      const ucode = detail.areas[areaIndex];
      return { key: stemOf(ucode), label: nameFor(ucode), value: source[i] ?? NaN };
    })
    .filter((r) => Number.isFinite(r.value))
    .sort((a, b) => b.value - a.value);

  const rows = all.slice(0, TOP_N);
  // A unit picked on the map may rank below the cut; show it rather than
  // leaving the selection invisible in this panel.
  const picked = selectedArea && all.find((r) => r.key === selectedArea);
  if (picked && !rows.includes(picked)) rows.push(picked);

  return (
    <>
      <p className="note">
        {t("bars.top", {
          n: Math.min(TOP_N, all.length),
          total: detail.areas.length,
          level,
          iso3,
        })}
      </p>
      <RankedBars
        rows={rows}
        unit={metric === "pct" ? "%" : "children"}
        highlight={selectedArea ? new Set([selectedArea]) : undefined}
        onSelect={(key) => setSelectedArea(key === selectedArea ? null : key)}
      />
    </>
  );
}

import { useEffect, useRef, useState } from "react";
// The CSP build plus an explicit worker URL, rather than the default build's
// blob: worker: a published page runs under a Content-Security-Policy that
// blocks blob workers, and the map would come up blank with no error worth
// reading. Vite emits the worker as an ordinary hashed asset.
import maplibregl from "maplibre-gl/dist/maplibre-gl-csp";
import workerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url";
import type { LngLatBounds, Map as MapLibreMap, MapMouseEvent, Point } from "maplibre-gl";

maplibregl.setWorkerUrl(workerUrl);
import { feature } from "topojson-client";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { colorFor, formatValue, quantileBreaks, NO_DATA } from "./scale";
import type { AdminLevel } from "./data/hazard";
import { loadCountryBoundaries } from "./data/boundaries";
import { useT } from "./i18n";

/** The admin-2 drilldown: one country's units drawn on top of the world.
 *  Keys are versionless ucode stems ("KEN_0012_0003") throughout, because the
 *  hazard database and GeoRepo can cite different versions of the same unit. */
export interface AreaLayer {
  iso3: string;
  /** 1 = counties, 2 = the units the database holds. Both files expose the
   *  join key as `stem`, so only the URL changes. */
  level: AdminLevel;
  /** stem -> value to paint. */
  values: Map<string, number>;
  /** Names for the tooltip. Admin-1 geometry is dissolved, so it carries no
   *  name of its own -- the caller resolves it. */
  nameFor?: (stem: string) => string;
  /** Class breaks for those values -- the drilldown has its own distribution,
   *  so it does not reuse the world map's. */
  breaks: number[];
  unit?: string;
  /** The one unit to outline and fly to. */
  focus?: string | null;
  onSelect?: (stem: string) => void;
}

/** Whether the drilldown geometry could be loaded, so the caller can say what
 *  to run when it is missing. */
export type AreaStatus = "off" | "loading" | "ok" | "missing";

/** Can this browser render the map at all?
 *
 *  MapLibre throws from its own constructor when there is no WebGL context, and
 *  that throw lands inside an effect, where React's answer is to unmount the
 *  whole tree -- a blank page rather than a broken map. Cheaper to ask first.
 *  MapLibre v4 removed `supported()`, so the probe is ours. */
function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

interface Props {
  /** iso3 -> value to paint. In continent mode every country in a continent
   *  carries that continent's value, so the paint logic stays identical. */
  values: Map<string, number>;
  unit?: string;
  /** iso3 codes currently selected, for the outline. */
  selectedIsos: string[];
  /** Called with the clicked country's iso3; the caller decides what that
   *  selects (the country, or its whole continent). */
  onSelect: (iso3: string) => void;
  /** Fit the view to these countries. Used to fly to a continent. */
  focusIsos?: string[] | null;
  /** Subnational units to draw over the country fill, or null for none. */
  areas?: AreaLayer | null;
  onAreaStatus?: (status: AreaStatus) => void;
  /** Fired when the zoom crosses the band where the finer level becomes
   *  worth drawing. Relative to the country fit, because "zoomed in" means
   *  something different for Luxembourg and Russia. */
  onLevelHint?: (level: AdminLevel) => void;
  /** Fired once when the map cannot be built here, so the caller can offer
   *  another way in: selecting a country is otherwise map-click only. */
  onUnsupported?: () => void;
  /** How many features in the active layer have no value, counted from what is
   *  actually painted rather than inferred from the value map. */
  onCoverage?: (scope: "world" | "area", noData: number, total: number) => void;
}

interface Hover {
  x: number;
  y: number;
  name: string;
  value?: number;
  unit?: string;
}

const SOURCE = "countries";
const AREA_SOURCE = "areas";
const AREA_LAYERS = ["area-fill", "area-border", "area-selected"];
const HOME = { center: [10, 20] as [number, number], zoom: 1.4 };

/** Bounding box of some features, skipping antimeridian outliers so Pacific
 *  territories don't stretch the box around the whole globe. */
function boundsOf(features: Feature<Geometry>[]): LngLatBounds | null {
  const bounds = new maplibregl.LngLatBounds();
  let found = false;
  for (const f of features) {
    const g = f.geometry as any;
    const rings: number[][][] =
      g?.type === "Polygon" ? g.coordinates : g?.type === "MultiPolygon" ? g.coordinates.flat() : [];
    for (const ring of rings) {
      for (const [lng, lat] of ring) {
        if (Math.abs(lng) > 179.5) continue;
        bounds.extend([lng, lat]);
        found = true;
      }
    }
  }
  return found ? bounds : null;
}

export default function WorldMap({
  values, unit, selectedIsos, onSelect, focusIsos, areas, onAreaStatus, onLevelHint,
  onUnsupported, onCoverage,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const geo = useRef<FeatureCollection<Geometry> | null>(null);
  const areaGeo = useRef<FeatureCollection<Geometry> | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;
  const pickArea = useRef(areas?.onSelect);
  pickArea.current = areas?.onSelect;
  const areaUnit = useRef(areas?.unit);
  areaUnit.current = areas?.unit;
  const status = useRef(onAreaStatus);
  status.current = onAreaStatus;
  const levelHint = useRef(onLevelHint);
  levelHint.current = onLevelHint;
  const unsupported = useRef(onUnsupported);
  unsupported.current = onUnsupported;
  const coverage = useRef(onCoverage);
  coverage.current = onCoverage;
  const areaName = useRef(areas?.nameFor);
  areaName.current = areas?.nameFor;
  /** Zoom the current country was fitted at, the baseline for the hint. */
  const baseZoom = useRef<number | null>(null);

  const { t } = useT();
  const [ready, setReady] = useState(false);
  const [noWebgl, setNoWebgl] = useState(false);
  const [areaReady, setAreaReady] = useState(false);
  const [hover, setHover] = useState<Hover | null>(null);

  // Build the map once. No basemap tiles: the boundaries are the map, so there
  // is nothing to fetch from a tile vendor.
  useEffect(() => {
    if (!container.current || map.current) return;
    if (!webglAvailable()) {
      setNoWebgl(true);
      unsupported.current?.();
      return;
    }

    let instance: MapLibreMap;
    try {
      instance = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#eef2f6" } }],
      },
      center: HOME.center,
      zoom: HOME.zoom,
      minZoom: 0.8,
      maxZoom: 9,
      dragRotate: false,
      attributionControl: false,
      });
    } catch {
      // A context can still fail to create on a browser that passes the probe
      // -- memory pressure, a blacklisted driver -- so never trust the probe
      // alone.
      setNoWebgl(true);
      unsupported.current?.();
      return;
    }

    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: "Boundaries: UNICEF GeoRepo (CC BY 4.0)",
      }),
    );
    instance.touchZoomRotate.disableRotation();
    map.current = instance;

    /** True when the drilldown covers this point, so the country underneath
     *  neither reports a hover nor swallows the click. */
    const overArea = (point: Point) =>
      !!instance.getLayer("area-fill") &&
      instance.queryRenderedFeatures(point, { layers: ["area-fill"] }).length > 0;

    (async () => {
      const response = await fetch("boundaries/adm0.min.topo.json");
      const topo = await response.json();
      const key = Object.keys(topo.objects)[0];
      geo.current = feature(topo, topo.objects[key]) as unknown as FeatureCollection<Geometry>;

      const addLayers = () => {
        instance.addSource(SOURCE, { type: "geojson", data: geo.current! });
        instance.addLayer({
          id: "fill",
          type: "fill",
          source: SOURCE,
          paint: { "fill-color": ["coalesce", ["get", "__color"], NO_DATA], "fill-opacity": 1 },
        });
        instance.addLayer({
          id: "border",
          type: "line",
          source: SOURCE,
          paint: { "line-color": "#ffffff", "line-width": 0.4 },
        });
        instance.addLayer({
          id: "selected",
          type: "line",
          source: SOURCE,
          filter: ["in", "iso3", ""],
          paint: { "line-color": "#0b0b0b", "line-width": 1.8 },
        });
        setReady(true);
      };
      if (instance.isStyleLoaded()) addLayers();
      else instance.on("load", addLayers);

      instance.on("mousemove", "fill", (event: MapMouseEvent & { features?: any[] }) => {
        const f = event.features?.[0];
        if (!f || overArea(event.point)) return;
        instance.getCanvas().style.cursor = "pointer";
        setHover({
          x: event.point.x,
          y: event.point.y,
          name: f.properties.name_en,
          value: f.properties.__value ?? undefined,
        });
      });
      instance.on("mouseleave", "fill", () => {
        instance.getCanvas().style.cursor = "";
        setHover(null);
      });
      instance.on("click", "fill", (event: MapMouseEvent & { features?: any[] }) => {
        if (overArea(event.point)) return;
        const iso3 = event.features?.[0]?.properties?.iso3;
        if (iso3) select.current(iso3);
      });

      // Registered up front; MapLibre resolves the layer at event time, so
      // these simply never fire while the drilldown is off.
      instance.on("mousemove", "area-fill", (event: MapMouseEvent & { features?: any[] }) => {
        const f = event.features?.[0];
        if (!f) return;
        instance.getCanvas().style.cursor = "pointer";
        setHover({
          x: event.point.x,
          y: event.point.y,
          name: areaName.current?.(f.properties.stem) ?? f.properties.name_en ?? f.properties.stem,
          value: f.properties.__value ?? undefined,
          unit: areaUnit.current,
        });
      });
      instance.on("mouseleave", "area-fill", () => {
        instance.getCanvas().style.cursor = "";
        setHover(null);
      });
      instance.on("click", "area-fill", (event: MapMouseEvent & { features?: any[] }) => {
        const stem = event.features?.[0]?.properties?.stem;
        if (stem) pickArea.current?.(stem);
      });

      // A bit more than one doubling past the country fit is where the finer
      // level starts to be legible rather than a mess of slivers.
      instance.on("zoomend", () => {
        const base = baseZoom.current;
        if (base === null) return;
        levelHint.current?.(instance.getZoom() >= base + 1.2 ? 2 : 1);
      });
    })();

    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  // Recolour whenever the values change.
  useEffect(() => {
    if (!ready || !geo.current || !map.current) return;
    const breaks = quantileBreaks([...new Set(values.values())]);
    let blank = 0;
    for (const f of geo.current.features) {
      const iso3 = (f.properties as any)?.iso3;
      const value = values.get(iso3);
      if (value === undefined) blank++;
      (f.properties as any).__value = value ?? null;
      (f.properties as any).__color = colorFor(value, breaks);
    }
    coverage.current?.("world", blank, geo.current.features.length);
    (map.current.getSource(SOURCE) as maplibregl.GeoJSONSource)?.setData(geo.current);
  }, [values, ready]);

  useEffect(() => {
    if (!ready || !map.current) return;
    map.current.setFilter("selected", [
      "in",
      "iso3",
      ...(selectedIsos.length ? selectedIsos : [""]),
    ]);
  }, [selectedIsos, ready]);

  // Fly to a continent when one is picked.
  useEffect(() => {
    if (!ready || !map.current || !geo.current) return;
    if (!focusIsos?.length) return;
    const wanted = new Set(focusIsos);
    const bounds = boundsOf(geo.current.features.filter((f) => wanted.has((f.properties as any)?.iso3)));
    if (!bounds) return;
    const instance = map.current;
    baseZoom.current = null;
    instance.fitBounds(bounds, { padding: 48, duration: 900, maxZoom: 5 });
    instance.once("moveend", () => {
      baseZoom.current = instance.getZoom();
    });
  }, [focusIsos, ready]);

  // --- Admin-2 drilldown ---------------------------------------------------
  // Geometry is per country (`etl/build_adm2.py KEN`): all 40,641 units
  // globally would mean vector tiles, one country's few hundred does not.
  const iso3 = areas?.iso3 ?? null;
  const level = areas?.level ?? 2;
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;

    const teardown = () => {
      for (const id of AREA_LAYERS) if (instance.getLayer(id)) instance.removeLayer(id);
      if (instance.getSource(AREA_SOURCE)) instance.removeSource(AREA_SOURCE);
      areaGeo.current = null;
      setAreaReady(false);
    };

    if (!iso3) {
      teardown();
      status.current?.("off");
      return;
    }

    let live = true;
    status.current?.("loading");
    (async () => {
      let topo: any = null;
      try {
        topo = await loadCountryBoundaries(iso3);
      } catch {
        topo = null;
      }
      if (!live) return;
      // Both levels live in one file, so switching level re-reads an object
      // that is already in memory rather than fetching anything.
      const object = topo?.objects?.[level === 1 ? "adm1" : "adm2"];
      if (!object) {
        teardown();
        status.current?.("missing");
        return;
      }
      if (!map.current) return;

      areaGeo.current = feature(topo, object) as unknown as FeatureCollection<Geometry>;

      if (!instance.getSource(AREA_SOURCE)) {
        instance.addSource(AREA_SOURCE, { type: "geojson", data: areaGeo.current });
        instance.addLayer({
          id: "area-fill",
          type: "fill",
          source: AREA_SOURCE,
          paint: { "fill-color": ["coalesce", ["get", "__color"], NO_DATA], "fill-opacity": 1 },
        });
        instance.addLayer({
          id: "area-border",
          type: "line",
          source: AREA_SOURCE,
          paint: { "line-color": "#ffffff", "line-width": 0.5 },
        });
        instance.addLayer({
          id: "area-selected",
          type: "line",
          source: AREA_SOURCE,
          filter: ["in", "stem", ""],
          paint: { "line-color": "#0b0b0b", "line-width": 2.2 },
        });
      } else {
        (instance.getSource(AREA_SOURCE) as maplibregl.GeoJSONSource).setData(areaGeo.current);
      }
      setAreaReady(true);
      status.current?.("ok");
      // No fit here: the caller zooms to the country on selection, and one
      // country's admin-2 extent is its country extent, so a second fit would
      // only fight the first for the same move.
    })();

    return () => {
      live = false;
    };
  }, [iso3, level, ready]);

  // Recolour the units. Same ramp as the world map, its own class breaks.
  useEffect(() => {
    if (!areaReady || !areaGeo.current || !map.current || !areas) return;
    let blank = 0;
    for (const f of areaGeo.current.features) {
      const stem = (f.properties as any)?.stem;
      const value = areas.values.get(stem);
      if (value === undefined) blank++;
      (f.properties as any).__value = value ?? null;
      (f.properties as any).__color = colorFor(value, areas.breaks);
    }
    coverage.current?.("area", blank, areaGeo.current.features.length);
    (map.current.getSource(AREA_SOURCE) as maplibregl.GeoJSONSource)?.setData(areaGeo.current);
  }, [areas?.values, areas?.breaks, areaReady]);

  // Outline the picked unit and fly to it -- at admin-2 a unit can be a few
  // kilometres across, so without the zoom the highlight is invisible.
  const focus = areas?.focus ?? null;
  useEffect(() => {
    if (!areaReady || !map.current || !areaGeo.current) return;
    map.current.setFilter("area-selected", ["in", "stem", ...(focus ? [focus] : [""])]);
    if (!focus || level === 1) return;
    const bounds = boundsOf(
      areaGeo.current.features.filter((f) => (f.properties as any)?.stem === focus),
    );
    // Up to the map's own ceiling: an admin-2 unit can be a few kilometres
    // across, and a unit that lands 60 px wide is not "shown" in any useful
    // sense. Larger units still fit on their own terms.
    if (bounds) map.current.fitBounds(bounds, { padding: 80, duration: 900, maxZoom: 9 });
  }, [focus, level, areaReady]);

  // No WebGL: say so where the map would be, and let the rest of the page work.
  // Silence here would read as a loading state that never resolves.
  if (noWebgl) {
    return (
      <div className="map-wrap">
        <div className="map-fallback">
          <strong>{t("map.needsWebgl")}</strong>
          <span>{t("map.webglHelp")}</span>
          <span>{t("map.webglRest")}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="map-wrap">
      <div ref={container} className="map" />
      <button
        className="map-reset"
        onClick={() => map.current?.easeTo({ ...HOME, duration: 700 })}
      >
        {t("map.reset")}
      </button>
      {hover && (
        <div className="tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          <strong>{hover.name}</strong>
          <span>
            {hover.value === undefined || hover.value === null
              ? t("map.noData", { count: "" }).replace(/\s*\(\s*\)\s*$/, "")
              : `${formatValue(hover.value)}${
                  (hover.unit ?? unit) ? ` ${hover.unit ?? unit}` : ""
                }`}
          </span>
        </div>
      )}
    </div>
  );
}

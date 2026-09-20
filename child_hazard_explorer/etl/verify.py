"""End-to-end checks on the built artifacts.

Run after the ETL:  python3 etl/verify.py
Exits non-zero if any check fails, so it can gate a build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from un_client import Rest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, detail: str = "") -> None:
    results.append((ok, name, detail))


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


BOUNDS = DATA / "boundaries"


def country_topologies() -> dict[str, dict]:
    """Per-country boundary topologies, from the chunks or the unbundled dir.

    Each holds both levels: objects `adm2` and `adm1`.
    """
    out: dict[str, dict] = {}
    index = BOUNDS / "country-index.json"
    if index.exists():
        for n in sorted(set(load(index).values())):
            chunk = BOUNDS / f"country-{n}.json"
            if chunk.exists():
                out.update(load(chunk))
        return out
    src = BOUNDS / "country"
    if src.exists():
        for f in src.glob("*.min.topo.json"):
            out[f.name.split(".")[0]] = load(f)
    return out


def stems_of(topo: dict, level: str) -> set[str]:
    obj = topo.get("objects", {}).get(level)
    if not obj:
        return set()
    return {g.get("properties", {}).get("stem") for g in obj["geometries"]}


def hazard_details() -> dict[str, dict]:
    """Admin-2 hazard detail per country.

    bundle_hazard.py packs the 229 per-country files into a dozen chunks and
    removes the directory, so read the chunks when they are there and fall back
    to the unbundled layout.
    """
    out: dict[str, dict] = {}
    index = DATA / "hazard" / "admin2-index.json"
    if index.exists():
        for n in sorted(set(load(index).values())):
            chunk = DATA / "hazard" / f"admin2-{n}.json"
            if chunk.exists():
                out.update(load(chunk))
        return out
    legacy = DATA / "hazard" / "admin2"
    if legacy.exists():
        for f in legacy.glob("*.json"):
            out[f.stem] = load(f)
    return out


def main() -> int:
    # --- 1. Corpus guard -----------------------------------------------------
    catalog_path = DATA / "catalog.json"
    if not catalog_path.exists():
        check(False, "catalog.json exists", "run build_catalog.py")
        return report()
    catalog = load(catalog_path)

    leaked = [d for d in catalog["names"] if not d.startswith("undata/")]
    check(not leaked, "every variable is undata/-scoped", f"{len(leaked)} leaked: {leaked[:3]}")

    check(len(catalog["goals"]) == 17, "17 SDG goals", f"got {len(catalog['goals'])}")
    check(bool(catalog["names"]), "catalog has variables", f"{len(catalog['names'])} found")

    # A hollow catalog is the failure mode that looks like success: goals and
    # targets present, variables silently missing because pagination was dropped.
    empty = [g.get("g") for g in catalog["goals"] if not g.get("c")]
    check(not empty, "no goal is empty", f"empty: {empty}")

    size_mb = catalog_path.stat().st_size / 1048576
    check(size_mb < 5, "catalog under 5 MB", f"{size_mb:.2f} MB")

    # --- 2. The federation regression ---------------------------------------
    # The wider graph answers 36.0 for Kenya 2021; the UN corpus answers 46.4.
    # If this ever flips, the app is quietly serving another publisher's numbers.
    rest = Rest()
    try:
        raw = rest.observations(
            "undata/sdg/SI_POV_DAY1", entities=["country/KEN"], date="LATEST"
        )
        facets = raw.get("facets", {})
        obs = (
            raw["byVariable"]["undata/sdg/SI_POV_DAY1"]["byEntity"]["country/KEN"]
            ["orderedFacets"][0]["observations"][0]
        )
        prov = next(iter(facets.values()), {}).get("provenanceId", "")
        check(
            abs(obs["value"] - 46.4) < 0.001 and obs["date"] == "2021",
            "Kenya SI_POV_DAY1 == 46.4 (2021), not the wider graph's 36.0",
            f"got {obs['value']} ({obs['date']})",
        )
        check(prov.startswith("undata/"), "provenance is UN-governed", f"got {prov!r}")
    except Exception as exc:  # noqa: BLE001
        check(False, "live observation check", str(exc))

    # --- 3. Places -----------------------------------------------------------
    places_path = DATA / "places.json"
    if places_path.exists():
        places = load(places_path)
        check(len(places["continents"]) == 6, "6 continents", str(len(places["continents"])))
        check(len(places["countries"]) > 200, "200+ countries", str(len(places["countries"])))
    else:
        check(False, "places.json exists", "run build_places.py")

    # --- 4. Boundary join ----------------------------------------------------
    topo_path = DATA / "boundaries" / "adm0.min.topo.json"
    hazard_path = DATA / "hazard" / "countries.json"
    if topo_path.exists():
        topo = load(topo_path)
        key = next(iter(topo["objects"]))
        geoms = topo["objects"][key]["geometries"]
        isos = {g.get("properties", {}).get("iso3") for g in geoms}
        check(len(geoms) > 200, "boundary features present", f"{len(geoms)} features")
        size_mb = topo_path.stat().st_size / 1048576
        check(size_mb < 10, "boundaries under 10 MB", f"{size_mb:.1f} MB")

        if hazard_path.exists():
            hazard = load(hazard_path)
            codes = set(hazard["countries"])
            matched = codes & isos
            rate = len(matched) / len(codes) if codes else 0
            check(
                rate > 0.9,
                "hazard ISO3 codes join to boundaries",
                f"{len(matched)}/{len(codes)} = {rate:.0%}",
            )
    else:
        check(False, "adm0.min.topo.json exists", "run build_boundaries.sh")

    # --- 5. Hazard -----------------------------------------------------------
    if hazard_path.exists():
        hazard = load(hazard_path)
        check(len(hazard["indicators"]) == 22, "22 hazard indicators",
              str(len(hazard["indicators"])))
        bad = [
            (c, i)
            for c, cd in hazard["countries"].items()
            for i, v in cd["indicators"].items()
            if v["pct"] is not None and not (0 <= v["pct"] <= 100.01)
        ]
        check(not bad, "exposure percentages in 0-100", f"{len(bad)} out of range")

    # --- 6. Admin-2 names join to the hazard ref_area codes ------------------
    import re

    names_path = DATA / "boundaries" / "adm2.names.json"
    details = hazard_details()
    if names_path.exists() and details:
        names = load(names_path)
        stem = {}
        for code, label in names.items():
            stem.setdefault(re.sub(r"_V\d+$", "", code), label)
        total = matched = 0
        for detail in details.values():
            areas = detail["areas"]
            total += len(areas)
            matched += sum(
                1 for a in areas if a in names or re.sub(r"_V\d+$", "", a) in stem
            )
        rate = matched / total if total else 0
        check(
            rate > 0.99,
            "admin-2 ucodes resolve to names",
            f"{matched:,}/{total:,} = {rate:.3%}",
        )

    # --- 6b. Drilldown geometry, where it has been built ---------------------
    # Optional and per country: an absent country means the drilldown is off
    # for it, not a broken build. What must hold is that the geometry present
    # joins to the hazard records, on the versionless stem. Reported in
    # aggregate -- 229 per-country lines would bury everything else.
    topologies = country_topologies()
    if topologies:
        wanted_total = joined_total = 0
        stacked: list[str] = []
        short: list[str] = []
        missing_adm1: list[str] = []
        for iso3, topo in sorted(topologies.items()):
            geoms = topo.get("objects", {}).get("adm2", {}).get("geometries", [])
            stems = stems_of(topo, "adm2")
            if len(stems) != len(geoms):
                stacked.append(iso3)
            if not stems_of(topo, "adm1"):
                missing_adm1.append(iso3)
            detail = details.get(iso3)
            if not detail:
                continue
            wanted = {re.sub(r"_V\d+$", "", a) for a in detail["areas"]}
            hit = wanted & stems
            wanted_total += len(wanted)
            joined_total += len(hit)
            if len(hit) != len(wanted):
                short.append(f"{iso3} {len(wanted) - len(hit)}")

        check(not stacked, "admin-2 geometry is one polygon per unit",
              f"stacked versions in {stacked[:3]}" if stacked
              else f"{len(topologies)} countries")
        rate = joined_total / wanted_total if wanted_total else 0
        check(rate > 0.99, "admin-2 hazard units have geometry",
              f"{joined_total:,}/{wanted_total:,} = {rate:.3%}"
              + (f", short: {short[:3]}" if short else ""))
        check(not missing_adm1, "every country carries both levels",
              f"no adm1 object in {missing_adm1[:3]}" if missing_adm1
              else f"{len(topologies)} countries")
        covered = len(topologies) / len(details) if details else 0
        check(True, "drilldown coverage",
              f"{len(topologies)}/{len(details)} countries built = {covered:.0%}")

        # Chunks are what actually ships; one runaway would blow the artifact
        # budget as surely as a runaway country file would.
        biggest = (0.0, "")
        for chunk in BOUNDS.glob("country-*.json"):
            if chunk.name == "country-index.json":
                continue
            size = chunk.stat().st_size / 1024
            if size > biggest[0]:
                biggest = (size, chunk.name)
        if biggest[1]:
            check(biggest[0] < 4096, "every boundary chunk under 4 MB",
                  f"largest {biggest[1]} {biggest[0]:,.0f} KB")

    # --- 6b2. Admin-1 roll-ups -----------------------------------------------
    # The database has no admin-1 rows; this level is derived. So check the
    # derivation, not just that a file exists: the units must have geometry,
    # and the numbers must still add up to the admin-2 records they came from.
    adm1_path = DATA / "hazard" / "adm1.json"
    if topologies and adm1_path.exists() and details:
        roll = load(adm1_path)
        no_geom = total1 = 0
        for iso3, entry in roll.items():
            topo = topologies.get(iso3)
            if not topo:
                continue
            stems = stems_of(topo, "adm1")
            total1 += len(entry["areas"])
            no_geom += len(set(entry["areas"]) - stems)
        check(not no_geom, "admin-1 roll-ups have geometry",
              f"{total1 - no_geom:,}/{total1:,} units")

        worst_sum = worst_pct = 0.0
        offender = ""
        unfilled = bad_cover = 0
        for iso3, entry in roll.items():
            detail = details.get(iso3)
            topo = topologies.get(iso3)
            if not detail or not topo:
                continue
            parents = {
                g["properties"].get("stem"): g["properties"].get("adm1")
                for g in topo["objects"]["adm2"]["geometries"]
            }
            for indicator, block in entry["indicators"].items():
                child = detail["indicators"].get(indicator)
                if not child:
                    continue
                kids = sum(
                    v for i, v in enumerate(child["exposed"])
                    if v is not None
                    and parents.get(re.sub(r"_V\d+$", "", detail["areas"][child["area"][i]]))
                )
                grown = sum(v for v in block["exposed"] if v is not None)
                gap = abs(kids - grown)
                if gap > worst_sum:
                    worst_sum, offender = gap, f"{iso3}/{indicator}"
                for i, pct in enumerate(block["pct"]):
                    pop, exposed = block["pop"][i], block["exposed"][i]
                    if pct is not None and pop:
                        worst_pct = max(worst_pct, abs(pct - exposed / pop * 100))
                    if not (1 <= block["units"][i] <= block["total"][i]):
                        bad_cover += 1
            # Every parent with a reporting child must have a value: a gap is
            # only allowed where NO child reported.
            for indicator, child in detail["indicators"].items():
                reporting = {
                    parents.get(re.sub(r"_V\d+$", "", detail["areas"][child["area"][i]]))
                    for i in range(len(child["area"]))
                }
                reporting.discard(None)
                block = entry["indicators"].get(indicator)
                have = {entry["areas"][a] for a in block["area"]} if block else set()
                unfilled += len(reporting - have)

        check(not unfilled, "every admin-1 area with reporting children has a value",
              f"{unfilled} left empty" if unfilled else "no gap is fillable")
        check(not bad_cover, "admin-1 coverage counts are within their parent",
              f"{bad_cover} out of range" if bad_cover else "1 <= units <= total")
        check(worst_sum <= total1, "admin-1 exposure sums to its admin-2 records",
              f"largest gap {worst_sum:,.0f} children ({offender})" if offender else "exact")
        check(worst_pct < 0.02, "admin-1 percentages re-derived from totals",
              f"largest drift {worst_pct:.4f} pp")

    # --- 6b3. Country totals against the rows they summarise --------------------
    # Two independent derivations of the same figure: countries.json comes from a
    # server-side facet over the whole database, the admin-2 chunks are the rows.
    # Nothing compared them until now, so a drift between the two would have
    # surfaced as a quiet contradiction in the UI rather than a failed build.
    if hazard_path.exists() and details:
        totals = load(hazard_path)["countries"]
        agree = differ = 0
        worst = []
        for iso3, detail in details.items():
            for indicator, cell in totals.get(iso3, {}).get("indicators", {}).items():
                block = detail["indicators"].get(indicator)
                reported = cell.get("exposed")
                if not block or reported is None:
                    continue
                summed = sum(v for v in block["exposed"] if v is not None)
                # Per-row rounding is the only difference allowed.
                if abs(summed - reported) <= max(1, 0.0005 * max(reported, 1)):
                    agree += 1
                else:
                    differ += 1
                    worst.append(f"{iso3}/{indicator} {reported:,} vs {summed:,}")
        check(
            not differ,
            "country totals equal the sum of their admin-2 records",
            f"{agree:,}/{agree + differ:,} cells" + (f", off: {worst[:2]}" if worst else ""),
        )

    # --- 6c. Hazard units ----------------------------------------------------
    units_path = DATA / "hazard" / "units.json"
    hazard_path_ok = hazard_path.exists()
    if units_path.exists() and hazard_path_ok:
        units = load(units_path)
        indicators = load(hazard_path)["indicators"]
        missing = [i for i in indicators if not units.get(i)]
        check(not missing, "every indicator has a hazard unit",
              f"{len(units)} units" if not missing else f"missing {missing[:3]}")

    # --- 7. No credentials in the built bundle -------------------------------
    dist = ROOT / "dist"
    if dist.exists():
        needles = ("solrread", "DAPMRead", "searchstax")
        hits = [
            str(p.relative_to(ROOT))
            for p in dist.rglob("*")
            if p.is_file() and p.suffix in {".js", ".html", ".css", ".json"}
            and any(n in p.read_text(encoding="utf-8", errors="ignore") for n in needles)
        ]
        check(not hits, "no Solr credentials in dist/", f"{hits[:3]}")

    return report()


def report() -> int:
    width = max(len(name) for _, name, _ in results) + 2
    failed = 0
    for ok, name, detail in results:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{mark}] {name:<{width}} {detail}")
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

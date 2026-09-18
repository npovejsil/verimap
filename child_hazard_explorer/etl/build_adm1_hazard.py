"""Roll the admin-2 hazard records up to admin-1.

The database has no admin-1 rows -- every one of its 5,415,036 records is
admin_level 2 -- but GeoRepo puts the parent admin-1 code on every admin-2
boundary, so the level is derivable. `build_adm2.py` keeps that parent and
dissolves the geometry; this does the same to the numbers.

How each column aggregates, and why:

  exposed  sum
  pop      sum
  pct      sum(exposed) / sum(pop), re-derived -- NEVER the mean of the
           children's percentages, which would weight a village like a city
  hazard   plain mean of the member units, matching the country roll-up's
           avg(hazard_mean) in build_hazard.py
  cls      max, matching that roll-up's max(country_exposure_class)
  units    how many admin-2 children this was actually computed from
  total    how many admin-2 children the parent has

Coverage is uneven and that is not visible in the result: 4,706 of the 71,962
admin-1 cells are computed from only *some* of their children, and the
percentage's denominator is then only the reporting units' population. So every
cell carries `units`/`total` and the app says which, rather than presenting a
partial aggregate as a whole one. Where a parent has no value at all (7,391
cells) it is because *none* of its children reported -- there is nothing to
aggregate, and the map leaves it as no-data rather than inventing a zero.

Output has the same columnar shape as a per-country admin-2 file, so the app
reads either level through one code path.

Usage:  python3 etl/build_adm1_hazard.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ADM2 = DATA / "boundaries" / "adm2"
OUT = DATA / "hazard" / "adm1.json"


def parents_for(iso3: str) -> dict[str, str]:
    """admin-2 stem -> admin-1 stem, read off the boundary file."""
    path = ADM2 / f"{iso3}.min.topo.json"
    if not path.exists():
        return {}
    topo = json.loads(path.read_text(encoding="utf-8"))
    geoms = topo["objects"][next(iter(topo["objects"]))]["geometries"]
    out = {}
    for geometry in geoms:
        props = geometry.get("properties") or {}
        stem, adm1 = props.get("stem"), props.get("adm1")
        if stem and adm1:
            out[stem] = adm1
    return out


def details() -> dict[str, dict]:
    index = json.loads((DATA / "hazard" / "admin2-index.json").read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for n in sorted(set(index.values())):
        chunk = DATA / "hazard" / f"admin2-{n}.json"
        if chunk.exists():
            out.update(json.loads(chunk.read_text(encoding="utf-8")))
    return out


def rollup(detail: dict, parents: dict[str, str], sizes: dict[str, int]) -> dict | None:
    stem_of = lambda u: u.rsplit("_V", 1)[0] if "_V" in u else u
    areas: list[str] = []
    area_index: dict[str, int] = {}
    indicators: dict[str, dict[str, list]] = {}

    for indicator, block in detail["indicators"].items():
        acc: dict[str, dict] = {}
        for i, area_i in enumerate(block["area"]):
            parent = parents.get(stem_of(detail["areas"][area_i]))
            if not parent:
                continue
            cell = acc.setdefault(
                parent, {"exposed": 0.0, "pop": 0.0, "hazard": [], "cls": [], "n": 0}
            )
            exposed, pop = block["exposed"][i], block["pop"][i]
            if exposed is not None:
                cell["exposed"] += exposed
            if pop is not None:
                cell["pop"] += pop
            if block["hazard"][i] is not None:
                cell["hazard"].append(block["hazard"][i])
            if block.get("cls") and block["cls"][i] is not None:
                cell["cls"].append(block["cls"][i])
            cell["n"] += 1
        if not acc:
            continue

        out = {"area": [], "exposed": [], "pop": [], "pct": [], "hazard": [],
               "cls": [], "units": [], "total": []}
        for parent, cell in sorted(acc.items()):
            if parent not in area_index:
                area_index[parent] = len(areas)
                areas.append(parent)
            out["area"].append(area_index[parent])
            out["exposed"].append(round(cell["exposed"]))
            out["pop"].append(round(cell["pop"]))
            out["pct"].append(
                round(cell["exposed"] / cell["pop"] * 100, 2) if cell["pop"] else None
            )
            out["hazard"].append(
                round(sum(cell["hazard"]) / len(cell["hazard"]), 5) if cell["hazard"] else None
            )
            out["cls"].append(max(cell["cls"]) if cell["cls"] else None)
            out["units"].append(cell["n"])
            out["total"].append(sizes.get(parent, cell["n"]))
        indicators[indicator] = out

    if not areas:
        return None
    return {"iso3": detail["iso3"], "areas": areas, "indicators": indicators}


def main() -> int:
    if not ADM2.exists():
        print("no admin-2 boundaries - run build_adm2.py --all first", file=sys.stderr)
        return 1

    all_detail = details()
    out: dict[str, dict] = {}
    skipped: list[str] = []
    for iso3 in sorted(all_detail):
        parents = parents_for(iso3)
        if not parents:
            skipped.append(iso3)
            continue
        sizes: dict[str, int] = {}
        for adm1 in parents.values():
            sizes[adm1] = sizes.get(adm1, 0) + 1
        rolled = rollup(all_detail[iso3], parents, sizes)
        if rolled:
            out[iso3] = rolled

    OUT.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    units = sum(len(c["areas"]) for c in out.values())
    partial = sum(
        1
        for c in out.values()
        for block in c["indicators"].values()
        for i, n in enumerate(block["units"])
        if n < block["total"][i]
    )
    print(f"  {partial:,} cells aggregated from only some of their children",
          file=sys.stderr)
    print(
        f"{len(out)} countries, {units:,} admin-1 units -> {OUT.relative_to(ROOT)} "
        f"({OUT.stat().st_size / 1048576:.1f} MB)",
        file=sys.stderr,
    )
    if skipped:
        print(f"  no boundaries for {len(skipped)}: {skipped[:5]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

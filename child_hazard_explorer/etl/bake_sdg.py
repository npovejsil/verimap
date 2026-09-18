"""Bake every SDG variable into static files the browser can read offline.

Why this exists: artifact pages block all cross-origin requests, so the live
API call that feeds the map fails there with `TypeError: Failed to fetch`.
Baking also makes the dashboard work offline and survive the API being down.

The API's JSON is verbose and most variables cover few countries, so the output
is columnar -- a shared place index plus parallel country/year/value arrays.
Measured on a 40-variable sample: 150 MB of raw JSON becomes 18.3 MB (4.7 MB
gzipped) for all 6,025 variables, which fits the budget with room to spare.

Requests batch ~20 variables at a time via repeated `variable.dcids`. Note that
comma-joining them silently returns only the first variable, so don't.

Usage:  python3 etl/bake_sdg.py [--batch 20] [--limit N] [--no-cache]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from un_client import Rest, assert_un_scoped

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sdg"
CACHE = ROOT / ".cache" / "bake"

ALL_COUNTRIES = "Earth<-containedInPlace+{typeOf:Country}"
CONTINENTS = ["africa", "asia", "europe", "northamerica", "southamerica", "oceania"]

# Keys drop the `undata/` prefix; the frontend puts it back. Saves ~7 bytes per
# key across 6,025 variables and keeps the files readable.
PREFIX = "undata/"


def short(dcid: str) -> str:
    return dcid[len(PREFIX):] if dcid.startswith(PREFIX) else dcid


def collect_variables(catalog: dict) -> dict[int, list[str]]:
    """goal number -> its variable dcids, in catalog order, deduped."""
    per_goal: dict[int, list[str]] = {}
    for goal in catalog["goals"]:
        seen: set[str] = set()
        ordered: list[str] = []

        def walk(node: dict) -> None:
            for dcid in node.get("v") or []:
                if dcid not in seen:
                    seen.add(dcid)
                    ordered.append(assert_un_scoped(dcid, "catalog"))
            for child in node.get("c") or []:
                walk(child)

        walk(goal)
        per_goal[goal["g"]] = ordered
    return per_goal


def fetch_batch(rest: Rest, batch: list[str], use_cache: bool) -> dict:
    """Full history for one batch, countries and continents merged.

    Omitting `date` is what returns every observation; `date=LATEST` would give
    only the most recent.
    """
    key = CACHE / (str(abs(hash(tuple(batch)))) + ".json")
    if use_cache and key.exists():
        return json.loads(key.read_text(encoding="utf-8"))

    merged: dict = {"byVariable": {}, "facets": {}}
    for params in (
        [("entity.expression", ALL_COUNTRIES)],
        [("entity.dcids", c) for c in CONTINENTS],
    ):
        query = [("variable.dcids", v) for v in batch] + params
        query += [("select", s) for s in ("date", "value", "variable", "entity")]
        doc = rest._get("observation", query)  # noqa: SLF001 - same package
        merged["facets"].update(doc.get("facets") or {})
        for var, block in (doc.get("byVariable") or {}).items():
            target = merged["byVariable"].setdefault(var, {"byEntity": {}})
            target["byEntity"].update(block.get("byEntity") or {})

    if use_cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps(merged), encoding="utf-8")
    return merged


def encode(
    doc: dict, places: list[str], index: dict[str, int], min_year: int = 0
) -> tuple[dict, dict]:
    """Columnar encode one response. Returns (series, units).

    `min_year` bounds the history. Full history came to 38.4 MB, which overflows
    the 64 MB artifact budget once the hazard and boundary files are counted;
    2010-onward is 27.5 MB and keeps 1.89M of 2.58M observations. Cutting at
    2000 instead saves almost nothing, so the data is overwhelmingly recent
    anyway -- and the SDGs were adopted in 2015 with baselines near 2010.
    """
    series: dict[str, dict] = {}
    units: dict[str, dict] = {}
    facets = doc.get("facets") or {}

    for dcid, block in (doc.get("byVariable") or {}).items():
        cols: list[int] = []
        years: list[int] = []
        values: list[float] = []
        facet_id = None
        for place, entry in (block.get("byEntity") or {}).items():
            ordered = entry.get("orderedFacets") or []
            if not ordered:
                continue
            best = ordered[0]  # the API ranks these; first is preferred
            facet_id = facet_id or best.get("facetId")
            name = place[8:] if place.startswith("country/") else place
            if name not in index:
                index[name] = len(places)
                places.append(name)
            slot = index[name]
            for obs in best.get("observations") or []:
                try:
                    year = int(str(obs["date"])[:4])
                except (KeyError, ValueError):
                    continue
                if year < min_year:
                    continue
                cols.append(slot)
                years.append(year)
                values.append(round(float(obs["value"]), 4))
        if not cols:
            continue
        key = short(dcid)
        series[key] = {"c": cols, "y": years, "v": values}
        facet = facets.get(facet_id or "", {})
        units[key] = {
            "unit": facet.get("unit"),
            "prov": facet.get("provenanceId"),
            "url": facet.get("provenanceUrl"),
        }
    return series, units


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0, help="only N variables (testing)")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument(
        "--min-year", type=int, default=2010, help="drop observations before this year"
    )
    args = ap.parse_args()

    catalog = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    per_goal = collect_variables(catalog)
    distinct = sorted({v for vs in per_goal.values() for v in vs})
    if args.limit:
        distinct = distinct[: args.limit]
        keep = set(distinct)
        per_goal = {g: [v for v in vs if v in keep] for g, vs in per_goal.items()}

    print(f"{len(distinct)} distinct variables across {len(per_goal)} goals", file=sys.stderr)

    rest = Rest()
    all_series: dict[str, dict] = {}
    all_units: dict[str, dict] = {}
    places: list[str] = []
    index: dict[str, int] = {}

    started = time.time()
    batches = [distinct[i : i + args.batch] for i in range(0, len(distinct), args.batch)]
    for n, batch in enumerate(batches, 1):
        try:
            doc = fetch_batch(rest, batch, not args.no_cache)
        except Exception as exc:  # noqa: BLE001 - one bad batch shouldn't kill the run
            print(f"  batch {n} failed: {exc}", file=sys.stderr)
            continue
        series, units = encode(doc, places, index, args.min_year)
        all_series.update(series)
        all_units.update(units)
        if n % 20 == 0 or n == len(batches):
            done = n / len(batches)
            elapsed = time.time() - started
            print(
                f"  {n}/{len(batches)} batches · {len(all_series)} vars · "
                f"{elapsed:.0f}s elapsed · ~{elapsed / done - elapsed:.0f}s left",
                file=sys.stderr,
            )

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d", time.gmtime())
    total = 0
    for goal, dcids in sorted(per_goal.items()):
        wanted = {short(d) for d in dcids}
        vars_ = {k: v for k, v in all_series.items() if k in wanted}
        # Each file carries only the places its own variables touch.
        used = sorted({i for s in vars_.values() for i in s["c"]})
        remap = {old: new for new, old in enumerate(used)}
        payload = {
            "goal": goal,
            "built": stamp,
            "minYear": args.min_year,
            "places": [places[i] for i in used],
            "vars": {
                k: {"c": [remap[i] for i in s["c"]], "y": s["y"], "v": s["v"]}
                for k, s in vars_.items()
            },
        }
        path = OUT / f"goal-{goal}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        total += path.stat().st_size
        print(f"  goal-{goal}.json  {len(vars_):>5} vars  {path.stat().st_size / 1024:>8.0f} KB",
              file=sys.stderr)

    meta = OUT / "units.json"
    meta.write_text(
        json.dumps({"built": stamp, "units": all_units}, separators=(",", ":")),
        encoding="utf-8",
    )
    total += meta.stat().st_size

    obs = sum(len(s["c"]) for s in all_series.values())
    print(
        f"\n{len(all_series)} variables, {obs:,} observations, "
        f"{total / 1048576:.1f} MB in {len(per_goal) + 1} files "
        f"({time.time() - started:.0f}s)",
        file=sys.stderr,
    )
    return 0 if all_series else 1


if __name__ == "__main__":
    raise SystemExit(main())

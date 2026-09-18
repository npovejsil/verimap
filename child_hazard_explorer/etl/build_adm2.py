"""Pull admin-2 boundaries out of GeoRepo, per country, for the map drilldown.

The hazard database is admin-2 throughout, so the map drops to that level once
a country is selected. GeoRepo publishes adm2 as a single 1.34 GB file, which
this never holds in memory: the file is one feature per line, so it streams and
each line is filed under its country as it goes.

Two phases, because only the first needs the network:

  1. stream  -> .cache/adm2-raw/<ISO3>.geojson   (full resolution, deduped)
  2. mapshaper -> data/boundaries/country/<ISO3>.min.topo.json (both levels)

Phase 2 is resumable: countries whose output already exists are skipped unless
--force, so a failed run costs minutes, not the download.

Versions are deduped to one polygon per unit, keeping `is_latest` where it
exists -- keeping every version, as build_area_names.py deliberately does,
would stack overlapping polygons on the map. The version suffix can still
disagree with the hazard database (README trap 3), so the browser joins on the
versionless stem rather than the full ucode.

Usage:  python3 etl/build_adm2.py --all          # every country with hazard data
        python3 etl/build_adm2.py KEN TZA
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://unidatadapmclimatechange.blob.core.windows.net/public/georepo"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / ".cache" / "adm2-raw"
# One file per country holding BOTH levels. TopoJSON shares an arc pool across
# objects, and admin-1 is dissolved from admin-2, so the coarser level rides
# along on arcs the finer one already paid for: Kenya is 147 KB for the pair
# against 244 KB as two files. It also halves the published file count.
OUT = ROOT / "data" / "boundaries" / "country"
# Most ucodes are ISO3_xxxx_xxxx_Vn, but GeoRepo also issues four-character
# prefixes for detached territories (PRT1 Azores, ESP1, UMI1-9, BES1-3): 56
# units that an [A-Z]{3}_ pattern drops on the floor. The country is still the
# first three characters.
UCODE = re.compile(rb'"ucode":\s*"([A-Z]{3}[0-9]?_[0-9A-Z_]*)"')
LATEST = re.compile(rb'"is_latest":\s*true')
VERSION = re.compile(r"_V\d+$")

stem_of = lambda ucode: VERSION.sub("", ucode)


def hazard_countries() -> list[str]:
    """The countries worth building: the ones the hazard database covers."""
    index = ROOT / "data" / "hazard" / "admin2-index.json"
    if not index.exists():
        raise SystemExit(f"{index} not found - run build_hazard.py + bundle_hazard.py")
    return sorted(json.loads(index.read_text(encoding="utf-8")))


def source_handle(local: Path):
    if local.exists():
        print(f"Scanning {local.name} ({local.stat().st_size / 1048576:,.0f} MB)...",
              file=sys.stderr)
        return local.open("rb")
    url = f"{BASE}/adm2.geojson"
    print(f"Streaming {url} ...", file=sys.stderr)
    return urllib.request.urlopen(url, timeout=3600)


def stream(wanted: set[bytes], local: Path) -> None:
    """One pass over the source, writing a raw GeoJSON slice per country.

    Every version is written here and the winners are chosen afterwards: which
    version wins is only known once the whole file has gone by, and the slices
    are small enough to re-read per country.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    handles: dict[bytes, object] = {}
    counts: dict[bytes, int] = {}
    read = kept = 0
    started = time.time()
    source = source_handle(local)
    try:
        for line in source:
            read += len(line)
            # Properties sit after the coordinates, so find the last "ucode" and
            # match from there rather than scanning megabytes of numbers.
            at = line.rfind(b'"ucode"')
            if at < 0:
                continue
            match = UCODE.match(line, at)
            if not match:
                continue
            code = match.group(1)[:3]
            if code not in wanted:
                continue
            handle = handles.get(code)
            if handle is None:
                handle = handles[code] = (RAW / f"{code.decode()}.jsonl").open("wb")
                counts[code] = 0
            handle.write(line if line.endswith(b"\n") else line + b"\n")
            counts[code] += 1
            kept += 1
            if read % (128 << 20) < len(line):
                rate = read / 1048576 / max(time.time() - started, 1)
                print(f"\r  {read / 1048576:,.0f} MB read, {kept:,} features kept, "
                      f"{len(handles)} countries, {rate:,.0f} MB/s", end="", file=sys.stderr)
    finally:
        for handle in handles.values():
            handle.close()
        source.close()
    print(f"\r  {read / 1048576:,.0f} MB read, {kept:,} features kept, "
          f"{len(handles)} countries" + " " * 20, file=sys.stderr)


def dedupe(iso3: str) -> tuple[Path, int] | None:
    """One feature per unit, preferring is_latest, as a FeatureCollection."""
    source = RAW / f"{iso3}.jsonl"
    if not source.exists():
        return None
    best: dict[str, dict] = {}
    with source.open("rb") as handle:
        for line in handle:
            match = UCODE.search(line)
            if not match:
                continue
            ucode = match.group(1).decode()
            stem = stem_of(ucode)
            latest = bool(LATEST.search(line))
            previous = best.get(stem)
            if previous is not None and not (latest and not previous["latest"]):
                continue
            best[stem] = {"latest": latest, "line": line}
    if not best:
        return None

    target = RAW / f"{iso3}.geojson"
    with target.open("w", encoding="utf-8") as out:
        out.write('{"type":"FeatureCollection","features":[\n')
        for i, (stem, row) in enumerate(sorted(best.items())):
            feature = json.loads(row["line"].rstrip(b",\n").decode("utf-8"))
            props = feature.get("properties") or {}
            adm1 = props.get("adm1_ucode") or ""
            feature["properties"] = {
                "ucode": props.get("ucode", ""),
                "stem": stem,
                "name_en": props.get("name_en") or props.get("name") or stem,
                "iso3": iso3,
                # The parent admin-1 unit. GeoRepo has no hazard data at that
                # level, but it carries the parent on every admin-2 feature, so
                # admin-1 is derivable by dissolving on this.
                "adm1": stem_of(adm1),
                "adm1_ucode": adm1,
            }
            out.write(("," if i else "") + json.dumps(feature, ensure_ascii=False) + "\n")
        out.write("]}\n")
    return target, len(best)


def simplify(iso3: str, source: Path, percent: str, binary: list[str]) -> Path:
    """Write both levels into one TopoJSON: objects `adm2` and `adm1`.

    Admin-1 is dissolved from the *already simplified* admin-2 geometry rather
    than from the source, so a county's outline is exactly the union of its
    sub-counties' outlines. Simplifying the two levels independently would
    leave them disagreeing by a pixel or two along every shared border.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"{iso3}.min.topo.json"
    # keep-shapes so small units survive simplification, and allow-overlaps so
    # -clean does not delete them afterwards: some countries' admin-2 units
    # overlap in the source, and plain -clean resolves that by dropping
    # polygons -- Saint Lucia came out with 106 of its 556 units, silently.
    subprocess.run(
        [*binary, "-i", "name=adm2", str(source),
         "-simplify", percent, "keep-shapes",
         "-clean", "allow-overlaps",
         "-dissolve", "adm1", "+", "name=adm1", "copy-fields=iso3,adm1_ucode",
         # Both levels expose the join key as `stem`, so the map paints either
         # one with the same code and the browser never branches on level.
         "-each", "stem=adm1", "target=adm1",
         "-o", "format=topojson", "quantization=1e5", "target=*", str(target)],
        check=True,
        capture_output=True,
        env={**os.environ, "NODE_OPTIONS": "--max-old-space-size=4096"},
    )
    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("iso3", nargs="*", help="ISO3 codes; omit with --all")
    ap.add_argument("--all", action="store_true", help="every country with hazard data")
    ap.add_argument("--simplify", default="4%")
    ap.add_argument("--source", help="local adm2.geojson (default: .cache, else stream)")
    ap.add_argument("--mapshaper", default="npx -y mapshaper",
                    help="mapshaper command (a resolved binary avoids npx startup)")
    ap.add_argument("--force", action="store_true", help="rebuild countries already built")
    ap.add_argument("--keep-raw", action="store_true", help="keep the .cache slices")
    args = ap.parse_args()

    codes = hazard_countries() if args.all else [c.upper() for c in args.iso3]
    if not codes:
        ap.error("name at least one ISO3, or pass --all")

    todo = codes if args.force else [
        c for c in codes if not (OUT / f"{c}.min.topo.json").exists()
    ]
    if not todo:
        print(f"all {len(codes)} countries already built", file=sys.stderr)
        return 0
    print(f"{len(todo)} of {len(codes)} countries to build", file=sys.stderr)

    missing = [c for c in todo if not (RAW / f"{c}.jsonl").exists()]
    if missing:
        stream({c.encode() for c in missing}, Path(args.source) if args.source
               else ROOT / ".cache" / "adm2.geojson")

    binary = args.mapshaper.split()
    built = failed = 0
    for n, iso3 in enumerate(todo, 1):
        deduped = dedupe(iso3)
        if deduped is None:
            print(f"  [{n}/{len(todo)}] {iso3}: no features", file=sys.stderr)
            failed += 1
            continue
        source, expected = deduped
        try:
            target = simplify(iso3, source, args.simplify, binary)
        except subprocess.CalledProcessError as exc:
            print(f"  [{n}/{len(todo)}] {iso3}: mapshaper failed - "
                  f"{exc.stderr.decode(errors='replace').strip()[:160]}", file=sys.stderr)
            failed += 1
            continue
        topo = json.loads(target.read_text(encoding="utf-8"))
        units = len(topo["objects"]["adm2"]["geometries"])
        parents = len(topo["objects"]["adm1"]["geometries"])
        # mapshaper can drop features without failing, which is how Saint Lucia
        # lost 450 units on the first build. Never trust the exit code alone.
        if units != expected:
            print(f"  [{n}/{len(todo)}] {iso3}: DROPPED {expected - units} of "
                  f"{expected} units in simplification", file=sys.stderr)
            failed += 1
            continue
        built += 1
        print(f"  [{n}/{len(todo)}] {iso3}: {units} adm2 in {parents} adm1, "
              f"{target.stat().st_size / 1024:,.0f} KB", file=sys.stderr)
        source.unlink(missing_ok=True)

    if not args.keep_raw:
        shutil.rmtree(RAW, ignore_errors=True)
    total = sum(p.stat().st_size for p in OUT.glob("*.min.topo.json")) / 1048576
    print(f"\n{built} built, {failed} failed; {OUT.name}/ is {total:.1f} MB",
          file=sys.stderr)
    return 1 if failed and not built else 0


if __name__ == "__main__":
    raise SystemExit(main())

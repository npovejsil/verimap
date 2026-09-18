"""Extract ucode -> name for admin-2 units, without loading 1.34 GB into memory.

The hazard records carry only `ref_area` codes (`EGY_0016_0001_V1`), no names
and no geometry. GeoRepo has the names, but adm2.geojson is 1.34 GB because it
holds full-resolution coordinates for every historical version of every
boundary. We want ~1% of that: one name per boundary version.

So this streams the file and pulls out just the `"properties": {...}` objects,
never parsing a coordinate array. Output is a flat {ucode: name} map.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = "https://unidatadapmclimatechange.blob.core.windows.net/public/georepo"
CHUNK = 8 << 20  # 8 MB reads

# Properties objects are flat (no nested braces), so a non-greedy match to the
# first closing brace is safe and avoids a real JSON parse of the geometry.
PROPS = re.compile(rb'"properties":\s*(\{[^{}]*\})')


def stream_names(path: Path, level: int) -> dict[str, str]:
    names: dict[str, str] = {}
    tail = b""
    read = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            read += len(chunk)
            buffer = tail + chunk
            last = 0
            for match in PROPS.finditer(buffer):
                last = match.end()
                try:
                    props = json.loads(match.group(1).decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                ucode = props.get("ucode")
                name = props.get("name_en") or props.get("name")
                if not ucode or not name:
                    continue
                # Keep EVERY version, not just is_latest. The hazard database
                # is pinned to whichever boundary version was current when it
                # was built: Solomon Islands records cite V2 while GeoRepo's
                # latest is V3, so an is_latest-only map misses all 50 of its
                # units. Versions are distinct ucodes, so nothing collides.
                if props.get("is_latest") or ucode not in names:
                    names[ucode] = name
            # Keep a tail in case a properties object straddles the boundary.
            tail = buffer[max(last, len(buffer) - 65536):]
            print(
                f"\r  {read / 1048576:,.0f} MB read, {len(names):,} names",
                end="",
                file=sys.stderr,
            )
    print(file=sys.stderr)
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", default="adm2")
    ap.add_argument("--keep", action="store_true", help="keep the raw download")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    source = cache / f"{args.level}.geojson"

    if not source.exists():
        url = f"{BASE}/{args.level}.geojson"
        print(f"Downloading {url} ...", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=1800) as response, source.open("wb") as out:
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                out.write(block)
                print(
                    f"\r  {source.stat().st_size / 1048576:,.0f} MB",
                    end="",
                    file=sys.stderr,
                )
        print(file=sys.stderr)

    level = int(args.level[-1])
    print(f"Scanning {source.name} ({source.stat().st_size / 1048576:,.0f} MB)...", file=sys.stderr)
    names = stream_names(source, level)

    out_path = root / "data" / "boundaries" / f"{args.level}.names.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(names, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(
        f"{len(names):,} names -> {out_path} ({out_path.stat().st_size / 1048576:.1f} MB)",
        file=sys.stderr,
    )

    if not args.keep:
        source.unlink()
        print(f"removed {source}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

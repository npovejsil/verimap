"""Bundle the 229 per-country admin-2 hazard files into a handful of chunks.

Per-country files are the nicest shape for lazy loading, but a published
artifact may hold at most 255 files and 229 of them for one optional drilldown
is a poor trade -- adding the 17 SDG goal files would have hit the cap.

Chunks are packed largest-first into the emptiest bin, because the countries are
wildly uneven (Brazil is 2.8 MB, Aruba is 1.6 KB); round-robin would leave one
chunk several megabytes fatter than the rest.

Usage:  python3 etl/bundle_hazard.py [--chunks 12]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "hazard" / "admin2"
OUT = ROOT / "data" / "hazard"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=int, default=12)
    ap.add_argument("--keep-source", action="store_true")
    args = ap.parse_args()

    files = sorted(SRC.glob("*.json"))
    if not files:
        print(f"nothing in {SRC} - run build_hazard.py first", file=sys.stderr)
        return 1

    # Largest first into the currently-smallest bin.
    sized = sorted(((p.stat().st_size, p) for p in files), reverse=True)
    bins: list[list[Path]] = [[] for _ in range(args.chunks)]
    loads = [0] * args.chunks
    for size, path in sized:
        i = loads.index(min(loads))
        bins[i].append(path)
        loads[i] += size

    index: dict[str, int] = {}
    total = 0
    for n, group in enumerate(bins):
        payload = {}
        for path in sorted(group):
            iso3 = path.stem
            payload[iso3] = json.loads(path.read_text(encoding="utf-8"))
            index[iso3] = n
        target = OUT / f"admin2-{n}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        total += target.stat().st_size
        print(
            f"  admin2-{n}.json  {len(payload):>3} countries  "
            f"{target.stat().st_size / 1024:>7.0f} KB",
            file=sys.stderr,
        )

    (OUT / "admin2-index.json").write_text(
        json.dumps(index, separators=(",", ":")), encoding="utf-8"
    )

    if not args.keep_source:
        shutil.rmtree(SRC)
        print(f"removed {SRC.relative_to(ROOT)} ({len(files)} files)", file=sys.stderr)

    print(
        f"\n{len(files)} files -> {args.chunks} chunks + index, "
        f"{total / 1048576:.1f} MB",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

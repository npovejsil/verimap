"""Pack the per-country boundary files into chunks the artifact limit allows.

A published artifact may hold at most 255 files, and one TopoJSON per country
is 229 of them before anything else is counted. Bundling solves that, but the
naive version trades it for a worse problem: with a dozen big chunks, opening
one country downloads two megabytes of other countries.

So the chunk count stays high (default 110) and packing is largest-first into
the emptiest bin, exactly as bundle_hazard.py does. Brazil ends up alone in its
chunk; a handful of small countries share one. Opening a country still fetches
roughly that country.

Usage:  python3 etl/bundle_boundaries.py [--chunks 110]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "boundaries" / "country"
OUT = ROOT / "data" / "boundaries"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=int, default=110)
    ap.add_argument("--keep-source", action="store_true")
    args = ap.parse_args()

    files = sorted(SRC.glob("*.min.topo.json"))
    if not files:
        print(f"nothing in {SRC} - run build_adm2.py --all first", file=sys.stderr)
        return 1

    for old in OUT.glob("country-*.json"):
        old.unlink()

    sized = sorted(((p.stat().st_size, p) for p in files), reverse=True)
    bins: list[list[Path]] = [[] for _ in range(args.chunks)]
    loads = [0] * args.chunks
    for size, path in sized:
        i = loads.index(min(loads))
        bins[i].append(path)
        loads[i] += size

    index: dict[str, int] = {}
    total = biggest = 0
    written = 0
    for n, group in enumerate(bins):
        if not group:
            continue
        payload = {}
        for path in sorted(group):
            iso3 = path.name.split(".")[0]
            payload[iso3] = json.loads(path.read_text(encoding="utf-8"))
            index[iso3] = n
        target = OUT / f"country-{n}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        size = target.stat().st_size
        total += size
        biggest = max(biggest, size)
        written += 1

    (OUT / "country-index.json").write_text(
        json.dumps(index, separators=(",", ":")), encoding="utf-8"
    )

    if not args.keep_source:
        shutil.rmtree(SRC)

    print(
        f"{len(files)} countries -> {written} chunks + index, {total / 1048576:.1f} MB "
        f"(largest chunk {biggest / 1024:,.0f} KB, mean {total / written / 1024:,.0f} KB)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

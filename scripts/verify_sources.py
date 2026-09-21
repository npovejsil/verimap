"""Check every API pull the catalog declares, grouped by source.

Run with: make verify-sources (or .venv/bin/python scripts/verify_sources.py)

Unlike scripts/verify_endpoints.py, this asserts no golden numbers. It checks
each pull for self-consistency against what the catalog claims -- units, value
range, place coverage, place id format -- so it stays meaningful as upstream
data updates instead of going stale the first time a source publishes a new
year. Exits 1 if any pull fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recipe.catalog import load_catalog
from recipe.source_checks import check_pull, summarize
from recipe.sources import load_sources

_MARK = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}


def main() -> None:
    catalog = load_catalog()
    sources = load_sources()
    all_checks = []

    for source_id, source in sources.items():
        indicators = [i for i in catalog.indicators.values() if i.source == source_id]
        print(f"\n{source.label}  <{source.base_url}>")
        print(f"  status={source.status} verified_on={source.verified_on}")
        if not indicators:
            print("  (no indicators declared for this source)")
            continue

        for indicator in sorted(indicators, key=lambda i: i.key):
            check = check_pull(indicator)
            all_checks.append(check)
            detail = (
                f"{check.n_places} places, latest {check.latest_date}, "
                f"{check.elapsed_ms}ms"
            )
            if check.upstream_source:
                detail += f", upstream: {check.upstream_source}"
            print(f"  [{_MARK[check.status]}] {indicator.key} — {detail}")
            if check.error:
                print(f"           {check.error}")
            for finding in check.findings:
                print(f"           ({finding.level}) {finding.code}: {finding.message}")

    counts = summarize(all_checks)
    print(
        f"\n{counts['pass']} passed, {counts['warn']} warned, {counts['fail']} failed "
        f"across {len(all_checks)} pulls."
    )
    if counts["fail"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

"""Shrink the crawled catalog into what the browser should actually download.

The raw crawl is ~46 MB, and almost all of it is repetition:

  themes    36.1 MB   44,387 nodes, 117,463 variable entries
  variables  6.0 MB   6,025 entries carrying a full ancestor-name path
  goals      2.7 MB   4,017 nodes, 7,633 variable entries

The themes axis spans the whole UN corpus (every agency), not just the SDGs, and
the same variable is repeated under many branches -- 125,096 entries for 84,893
distinct dcids. So: keep each variable's name once in a lookup, reference it by
dcid in the tree, and split themes into their own lazily-loaded file.

Run after build_catalog.py, or let build_catalog.py call it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def compact(node: dict, names: dict[str, str]) -> dict:
    """Tree node -> {d, n, c?, v?} with variable names hoisted into `names`."""
    out: dict = {"d": node["dcid"], "n": node["name"]}
    for var in node["variables"]:
        names.setdefault(var["dcid"], var["name"])
    variables = [v["dcid"] for v in node["variables"]]
    if variables:
        out["v"] = variables
    children = [compact(c, names) for c in node["children"]]
    if children:
        out["c"] = children
    return out


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".cache" / "catalog.full.json"
    raw = json.loads(source.read_text(encoding="utf-8"))

    goal_names: dict[str, str] = {}
    goals = []
    for goal in raw["goals"]:
        entry = compact(goal, goal_names)
        entry["g"] = goal["number"]
        goals.append(entry)

    theme_names: dict[str, str] = {}
    themes = [compact(t, theme_names) for t in raw["themes"]]

    bad = [d for d in {**goal_names, **theme_names} if not d.startswith("undata/")]
    if bad:
        raise SystemExit(f"FATAL: non-UN identifiers present: {bad[:5]}")

    # The themes axis indexes the whole UN corpus (every agency), not just the
    # SDGs: 84,893 variables and ~34 MB. That is not something to make every
    # visitor download for a secondary navigation axis, so it stays in .cache
    # unless explicitly published with --with-themes.
    publish_themes = "--with-themes" in sys.argv
    out_dir = ROOT / "data"
    catalog = {
        "source": raw["source"],
        "built": raw["built"],
        "goals": goals,
        "names": goal_names,
    }
    themes_doc = {"themes": themes, "names": theme_names}

    themes_path = (out_dir if publish_themes else ROOT / ".cache") / "themes.json"
    for path, payload in ((out_dir / "catalog.json", catalog), (themes_path, themes_doc)):
        path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        print(f"  {path.name:<14} {path.stat().st_size / 1048576:6.2f} MB", file=sys.stderr)

    print(
        f"goals={len(goals)} goal-variables={len(goal_names)} "
        f"themes={len(themes)} theme-variables={len(theme_names)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

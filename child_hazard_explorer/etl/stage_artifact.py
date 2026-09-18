"""Prepare `dist/` for publishing as a single shareable page.

Two limits shape this: a published artifact holds at most 255 files and 64 MB
per version, and `dist/` as built is 501 files and 132 MB. Getting under them is
not a matter of deleting things the app needs:

  - the retired SDG artifacts (`sdg/`, `catalog.json`) are 39 MB that nothing
    loads any more, so they are dropped from the *bundle*, not the repo
  - boundaries ship as one file per country holding both levels, then bundled
    into chunks by `bundle_boundaries.py`
  - the page itself is written here, because the artifact host supplies the
    document skeleton: this file is the page's *content*, starting at <title>,
    and it has to name whatever hashed asset filenames vite just emitted

Run after `npm run build`. Prints the manifest and what the budget looks like.

Usage:  python3 etl/stage_artifact.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
# Everything the retired SDG side put in the bundle.
RETIRED = ["sdg", "catalog.json"]
MAX_FILES = 255
MAX_BYTES = 64 * 1024 * 1024

PAGE = """<title>Child Hazard Explorer</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Condensed:wght@400;700&display=swap"
  rel="stylesheet"
/>
<link rel="stylesheet" href="{css}" />
<div id="root"></div>
<script type="module" src="{js}"></script>
"""


def main() -> int:
    if not DIST.exists():
        print("no dist/ - run npm run build first", file=sys.stderr)
        return 1

    for name in RETIRED:
        target = DIST / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    assets = sorted((DIST / "assets").glob("*"))
    css = next((a for a in assets if a.suffix == ".css"), None)
    js = next((a for a in assets if a.name.startswith("index-") and a.suffix == ".js"), None)
    if not css or not js:
        print("could not find the built css/js in dist/assets", file=sys.stderr)
        return 1

    page = DIST / "artifact.html"
    page.write_text(
        PAGE.format(css=f"assets/{css.name}", js=f"assets/{js.name}"), encoding="utf-8"
    )

    # Everything except the page itself and vite's own index.html, which the
    # artifact host replaces.
    # Dotfiles (.DS_Store and friends) ride along from the source tree and are
    # neither wanted nor a servable media type.
    files = [
        p for p in sorted(DIST.rglob("*"))
        if p.is_file()
        and p.name not in {"artifact.html", "index.html", "artifact-manifest.json"}
        and not any(part.startswith(".") for part in p.relative_to(DIST).parts)
    ]
    manifest = {str(p.relative_to(DIST)): str(p.relative_to(DIST)) for p in files}
    (DIST / "artifact-manifest.json").write_text(
        json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8"
    )

    total = sum(p.stat().st_size for p in files) + page.stat().st_size
    count = len(files) + 1
    biggest = max(files, key=lambda p: p.stat().st_size)

    print(f"page     : {page.relative_to(ROOT)}", file=sys.stderr)
    print(f"files    : {count} / {MAX_FILES}", file=sys.stderr)
    print(f"size     : {total / 1048576:.1f} MB / {MAX_BYTES / 1048576:.0f} MB", file=sys.stderr)
    print(f"largest  : {biggest.relative_to(DIST)} "
          f"{biggest.stat().st_size / 1048576:.1f} MB", file=sys.stderr)
    for name, pat in [("boundaries", "boundaries/*"), ("hazard", "hazard/*"),
                      ("assets", "assets/*")]:
        size = sum(p.stat().st_size for p in DIST.glob(pat) if p.is_file())
        print(f"  {name:11s} {size / 1048576:6.1f} MB", file=sys.stderr)

    over = []
    if count > MAX_FILES:
        over.append(f"{count - MAX_FILES} files over")
    if total > MAX_BYTES:
        over.append(f"{(total - MAX_BYTES) / 1048576:.1f} MB over")
    if over:
        print("OVER BUDGET: " + ", ".join(over), file=sys.stderr)
        return 1
    print("within budget", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

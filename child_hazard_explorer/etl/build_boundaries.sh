#!/usr/bin/env bash
# GeoRepo GeoJSON -> small TopoJSON the browser can actually load.
#
# The source files are full-resolution AND carry every historical version of
# each boundary (adm0 213 MB, adm1 514 MB, adm2 1.34 GB), so two things must
# happen before the web app sees them: filter to is_latest, and simplify.
#
# Usage:  ./etl/build_boundaries.sh adm0 [percent]
# Needs:  npx (mapshaper is fetched on demand; no global install)

set -euo pipefail

LEVEL="${1:-adm0}"
PCT="${2:-8%}"
BASE="https://unidatadapmclimatechange.blob.core.windows.net/public/georepo"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Raw downloads stay in .cache (hundreds of MB, never published); only the
# simplified file lands in data/, which is the app's served directory.
CACHE="$ROOT/.cache"
DIR="$ROOT/data/boundaries"
SRC="$CACHE/$LEVEL.geojson"
OUT="$DIR/$LEVEL.min.topo.json"

mkdir -p "$DIR" "$CACHE"

if [[ ! -f "$SRC" ]]; then
  echo "Downloading $LEVEL..."
  curl -fL --progress-bar "$BASE/$LEVEL.geojson" -o "$SRC"
fi

echo "Source: $(du -h "$SRC" | cut -f1)"
echo "Filtering to is_latest, trimming fields, simplifying to $PCT..."

# keep-shapes stops small island states collapsing to nothing at low percentages.
NODE_OPTIONS=--max-old-space-size=8192 npx -y mapshaper "$SRC" \
  -filter 'is_latest === true' \
  -each 'iso3 = (this.properties.ISO3 || this.properties.adm0_ucode || this.properties.ucode || "").slice(0,3)' \
  -filter-fields ucode,name_en,iso3,level \
  -simplify "$PCT" keep-shapes \
  -clean \
  -o format=topojson quantization=1e4 "$OUT"

echo "Output: $OUT ($(du -h "$OUT" | cut -f1))"

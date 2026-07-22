#!/usr/bin/env bash
# Build the Aykiz family from the rounded UFO masters in this directory.
#
#   ./build.sh            build fonts from the committed rounded masters
#   ./build.sh regen      first regenerate the rounded masters from upstream
#                         Montserrat (clones it), then build
#
# Requires: fontmake, fonttools, ufoLib2 (pip install fontmake).
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${1:-}" == "regen" ]]; then
  if [[ ! -d montserrat ]]; then
    git clone --depth 1 https://github.com/googlefonts/montserrat.git montserrat
  fi
  python prepare_sources.py montserrat/sources
fi

TTF=../fonts/ttf
mkdir -p "$TTF"

echo "== static instances =="
fontmake -m Aykiz.designspace        -i -o ttf --output-dir "$TTF"
fontmake -m Aykiz-Italic.designspace -i -o ttf --output-dir "$TTF"

echo "== name / metadata normalisation =="
python fix_names.py "$TTF"

# Insert on-curve extrema. On the Google Fonts toolchain the source's AddExtremes
# filter already does this at build time and this pass is a no-op; it is included
# so the family also builds clean on a plain fontmake install.
echo "== extrema pass =="
python add_extremes.py "$TTF"

# A variable font can be built from the same sources if desired:
#   fontmake -m Aykiz.designspace        -o variable --output-path ../fonts/variable/'Aykiz[wght].ttf'
#   fontmake -m Aykiz-Italic.designspace -o variable --output-path ../fonts/variable/'Aykiz-Italic[wght].ttf'

echo "done."

#!/bin/sh
# Rebuild the Aykiz family from upstream Montserrat statics.
# Requires: python3 with fonttools + shapely  (pip install fonttools shapely)
set -e
mkdir -p ../fonts/ttf upstream
for spec in Thin:6 ThinItalic:6 ExtraLight:8 ExtraLightItalic:8 Light:10 LightItalic:10 \
            Regular:12 Italic:12 Medium:12 MediumItalic:12 SemiBold:12 SemiBoldItalic:12 \
            Bold:12 BoldItalic:12 ExtraBold:13 ExtraBoldItalic:13 Black:14 BlackItalic:14; do
  s="${spec%%:*}"; r="${spec##*:}"
  [ -f "upstream/Montserrat-$s.ttf" ] || curl -sfL -o "upstream/Montserrat-$s.ttf" \
    "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-$s.ttf"
  python3 round_font.py "upstream/Montserrat-$s.ttf" "../fonts/ttf/Aykiz-$s.ttf" "Aykiz" "$r"
done

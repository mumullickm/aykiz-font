# Aykiz

Aykiz is a geometric sans-serif family with gently rounded corners — warm at
display sizes, invisible-softness at text sizes. 18 styles: 9 weights
(Thin 100 → Black 900) plus matching italics. Full Montserrat character set:
extended Latin, Vietnamese, and Cyrillic (1,000+ glyphs per style), with all
original spacing and kerning intact.

**Aykiz is an open-source derivative of
[Montserrat](https://github.com/JulietaUla/Montserrat)** by Julieta Ulanovsky
and the Montserrat Project Authors, released — like Montserrat itself — under
the [SIL Open Font License 1.1](OFL.txt). We say this proudly and up front:
the OFL exists precisely so that type can evolve. Per the license, the
derivative does not use the reserved name "Montserrat", and the original
copyright and license travel with these files.

## What was changed

Every glyph outline is processed with a curve-preserving corner-rounding
filter (v1.1). Montserrat's original quadratic beziers are kept untouched;
corners are detected by tangent discontinuity (>22°), the two adjacent
segments are trimmed back by the radius, and each corner is bridged with a
single true quadratic curve whose control point is the original corner. No
outline is ever flattened: straight edges stay lines, curves stay curves,
and point counts stay close to the original (the Regular B is 55 points vs
Montserrat's 33, versus 131 line-only points in the withdrawn v1.0 filter).
The radius scales with weight so the softness is optically consistent and
thin strokes are never damaged:

| Weight | Radius (per 1000 UPM) |
|---|---|
| Thin | 6 |
| ExtraLight | 8 |
| Light | 10 |
| Regular–Bold | 12 |
| ExtraBold | 13 |
| Black | 14 |

Metrics, sidebearings, kerning (GPOS), OpenType features, and the character
map are inherited unchanged from Montserrat. TrueType hinting was removed
(outlines changed; modern rasterizers don't need it).

## Structure

```
fonts/ttf/          18 static TTFs
sources/            round_font.py + build.sh — fully reproducible build
OFL.txt             license (original + derivative copyright)
specimen.html       self-contained preview, open in any browser
```

## Rebuild from source

```sh
cd sources && ./build.sh
```

Downloads upstream Montserrat statics and regenerates every Aykiz style.
Change the radii in `build.sh` to taste.

## Use it

- **Web**: self-host the TTFs (or convert to WOFF2: `pip install fonttools brotli`,
  then `fonttools ttLib.woff2 compress <file>`).
- **macOS/iOS/Android apps**: bundle the TTFs directly.
- The name "Aykiz" is not a reserved font name; forks are welcome under the OFL.

## Google Fonts

Submission to Google Fonts must disclose the Montserrat derivation (their
onboarding checks provenance, and honesty is the whole point). Be aware that
Google Fonts generally prioritizes original designs or substantial expansions
over light derivatives of fonts already in the catalog — acceptance is their
editorial call. This repo follows their expected layout (OFL, sources,
reproducible build) so a submission is ready if pursued.

## Credits

- Original design: Julieta Ulanovsky and the Montserrat Project Authors
- Corner-rounding derivative "Aykiz": Miraz Mullick, 2026

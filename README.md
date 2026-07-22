# Aykiz

Aykiz is a geometric sans-serif family with gently rounded corners, warm at
display sizes and quietly soft at text sizes. 18 styles: 9 weights
(Thin 100 to Black 900) plus matching italics. It inherits Montserrat's full
character set (extended Latin, Vietnamese, Cyrillic), spacing, and kerning.

**Aykiz is an open-source derivative of
[Montserrat](https://github.com/JulietaUla/Montserrat)** by Julieta Ulanovsky
and the Montserrat Project Authors, released, like Montserrat itself, under the
[SIL Open Font License 1.1](OFL.txt). Per the license, the derivative does not
use the reserved name "Montserrat", and the original copyright and license
travel with these files.

## How it is built (this is the important part)

Aykiz is built **from Montserrat's own UFO sources**, not by post-processing the
binary fonts. The pipeline is:

1. Montserrat's interpolation masters (`Thin`, `SemiBold`, `Black`, plus the
   three matching italics) are used as the sources.
2. A corner-rounding filter fillets the sharp **line-to-line** corners on those
   masters, replacing each with a **true circular cubic Bézier arc**. Existing
   curves and smooth (tangent) joins are left untouched, so bowls stay bowls and
   only the rectilinear corners soften.
3. The set of corners to round is decided once from a mid-weight reference master
   and applied identically to every master, so the masters stay point-compatible
   and interpolate cleanly.
4. `fontmake` interpolates the 18 instances from the rounded masters.

The radius scales with weight (≈25% of the vertical stem) so the softness is
optically consistent and thin strokes are never damaged:

| Master   | Fillet radius (1000 UPM) |
|----------|--------------------------|
| Thin     | 6                        |
| SemiBold | 28                       |
| Black    | 58                       |

Intermediate weights interpolate between these. Metrics, sidebearings, kerning
(GPOS), OpenType features, and the character map are inherited unchanged from
Montserrat.

## Sources and reproducible build

```
sources/
  Aykiz-Thin.ufo  Aykiz-SemiBold.ufo  Aykiz-Black.ufo         # rounded masters
  Aykiz-ThinItalic.ufo  Aykiz-SemiBoldItalic.ufo  Aykiz-BlackItalic.ufo
  Aykiz.designspace  Aykiz-Italic.designspace
  round_corners.py    # the corner-rounding filter (documented)
  prepare_sources.py  # regenerates the rounded masters from upstream Montserrat
  build.sh            # prepare + fontmake + name fixup
fonts/ttf/            # 18 static TTFs
OFL.txt               # license (original + derivative copyright)
```

The `sources/*.ufo` are the rounded masters and are the source of record: a
reviewer can build the family directly with `fontmake -m sources/Aykiz.designspace -i`.
To regenerate the rounded masters from a fresh Montserrat checkout instead, run
`sources/prepare_sources.py` (see `build.sh`).

```sh
cd sources && ./build.sh
```

## Credits

- Original design: Julieta Ulanovsky and the Montserrat Project Authors
- Corner-rounded derivative "Aykiz": Miraz Mullick, 2026

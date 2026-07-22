"""Regenerate the rounded Aykiz masters from an upstream Montserrat checkout.

The committed sources/Aykiz-*.ufo ARE the source of record; run this only to
rebuild them from a fresh Montserrat. Usage:

    python prepare_sources.py [path/to/montserrat/sources]

Defaults to ./montserrat/sources (see build.sh, which clones it).
Writes Aykiz-*.ufo and Aykiz*.designspace next to this script.
"""
import os
import shutil
import sys

import ufoLib2
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("rc", os.path.join(HERE, "round_corners.py"))
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "montserrat", "sources")
OUT = HERE

RADII = {"Thin": 6.0, "SemiBold": 28.0, "Black": 58.0,
         "ThinItalic": 6.0, "SemiBoldItalic": 28.0, "BlackItalic": 58.0}
GROUPS = [(["Thin", "SemiBold", "Black"], 1),
          (["ThinItalic", "SemiBoldItalic", "BlackItalic"], 1)]
DESIGNSPACES = ["Montserrat.designspace", "Montserrat-Italic.designspace"]


def main():
    for m in RADII:
        dst = os.path.join(OUT, f"Aykiz-{m}.ufo")
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(SRC, f"Montserrat-{m}.ufo"), dst)

    for masters, ref_idx in GROUPS:
        paths = [os.path.join(OUT, f"Aykiz-{m}.ufo") for m in masters]
        rmap = {os.path.join(OUT, f"Aykiz-{m}.ufo"): RADII[m] for m in masters}
        dec = rc.round_masters(paths, ref_idx, rmap)
        print(f"rounded {masters} (ref={masters[ref_idx]}): {len(dec)} glyphs")

    for m in RADII:
        p = os.path.join(OUT, f"Aykiz-{m}.ufo")
        font = ufoLib2.Font.open(p)
        for attr in ("familyName", "styleMapFamilyName",
                     "openTypeNameCompatibleFullName", "openTypeNamePreferredFamilyName"):
            v = getattr(font.info, attr, None)
            if v and "Montserrat" in v:
                setattr(font.info, attr, v.replace("Montserrat", "Aykiz"))
        font.save(p, overwrite=True)

    for ds in DESIGNSPACES:
        txt = open(os.path.join(SRC, ds)).read().replace("Montserrat", "Aykiz")
        open(os.path.join(OUT, ds.replace("Montserrat", "Aykiz")), "w").write(txt)
    print("wrote designspaces")


if __name__ == "__main__":
    main()

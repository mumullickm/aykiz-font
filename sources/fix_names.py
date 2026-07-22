"""Post-build name/OS2/version normalisation for the Aykiz TTFs.

Sets consistent family/subfamily/full/PostScript names, version 2.000, OFL
copyright + license, designer/manufacturer, vendor URL, fsType installable.
RIBBI grouping: Regular/Bold/Italic/Bold Italic share family 'Aykiz'; other
weights use the weight in the typographic (16/17) names and a WWS-style family
in the legacy (1/2) names so old apps list all 18 styles.
"""
import glob
import os
import sys

from fontTools.ttLib import TTFont

VERSION = "2.000"
COPYRIGHT = ("Copyright 2026 Miraz Mullick (Aykiz, a corner-rounded derivative). "
             "Portions Copyright 2011 The Montserrat Project Authors "
             "(https://github.com/JulietaUla/Montserrat), with Reserved Font Name Montserrat.")
DESIGNER = "Miraz Mullick; Julieta Ulanovsky and the Montserrat Project Authors (original)"
DESIGNER_URL = "https://github.com/mumullickm"
VENDOR_URL = "https://github.com/mumullickm/aykiz-font"
LICENSE = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
           "This license is available with a FAQ at https://openfontlicense.org")
LICENSE_URL = "https://openfontlicense.org"

RIBBI = {"Regular", "Bold", "Italic", "Bold Italic"}


def set_name(name, nameID, value):
    name.setName(value, nameID, 3, 1, 0x409)  # Windows
    name.setName(value, nameID, 1, 0, 0)      # Mac


def style_from_filename(path):
    base = os.path.basename(path).replace(".ttf", "")
    style = base.split("-", 1)[1] if "-" in base else "Regular"
    # keep weight tokens solid (SemiBold, ExtraBold, ExtraLight); only split a
    # trailing Italic, e.g. SemiBoldItalic -> "SemiBold Italic", Italic -> "Italic"
    if style != "Italic" and style.endswith("Italic"):
        style = style[:-len("Italic")] + " Italic"
    return style


def fix(path):
    f = TTFont(path)
    name = f["name"]
    style = style_from_filename(path)          # e.g. "SemiBold", "Bold Italic", "Thin Italic"
    is_italic = style.endswith("Italic")
    weight = style.replace("Italic", "").strip() or "Regular"

    typo_family = "Aykiz"
    typo_sub = style if style else "Regular"

    # legacy RIBBI: keep all 18 discoverable in old apps
    if style in RIBBI:
        legacy_family = "Aykiz"
        legacy_sub = style
    else:
        legacy_family = f"Aykiz {weight}".strip()
        legacy_sub = "Italic" if is_italic else "Regular"

    full = f"Aykiz {typo_sub}".replace("Aykiz Regular", "Aykiz")
    ps = ("Aykiz-" + typo_sub.replace(" ", ""))

    set_name(name, 0, COPYRIGHT)
    set_name(name, 1, legacy_family)
    set_name(name, 2, legacy_sub)
    set_name(name, 3, f"{VERSION};AYKZ;{ps}")
    set_name(name, 4, full)
    set_name(name, 5, f"Version {VERSION}")
    set_name(name, 6, ps)
    set_name(name, 9, DESIGNER)
    set_name(name, 11, VENDOR_URL)
    set_name(name, 12, DESIGNER_URL)
    set_name(name, 13, LICENSE)
    set_name(name, 14, LICENSE_URL)
    set_name(name, 16, typo_family)
    set_name(name, 17, typo_sub)

    if "head" in f:
        f["head"].fontRevision = float(VERSION)
    if "OS/2" in f:
        f["OS/2"].fsType = 0  # installable embedding
    if "OS/2" in f and hasattr(f["OS/2"], "achVendID"):
        f["OS/2"].achVendID = "AYKZ"

    f.save(path)
    return f"{os.path.basename(path):28s} family='{legacy_family}' sub='{legacy_sub}' typo='{typo_family}/{typo_sub}'"


if __name__ == "__main__":
    d = sys.argv[1]
    for p in sorted(glob.glob(os.path.join(d, "*.ttf"))):
        print(fix(p))

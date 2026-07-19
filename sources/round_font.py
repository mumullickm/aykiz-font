"""Apply subtle corner-rounding to an existing TTF (e.g. Montserrat).

Keeps metrics/kerning/cmap; only glyph outlines are filtered.
Method: flatten quadratic outlines to fine polylines, then morphological
rounding: buffer(+R) -> buffer(-2R) -> buffer(+R) with round joins, which
rounds convex AND concave corners with radius ~R while leaving straight
edges and existing curves essentially untouched.
"""
import math
import sys

from shapely.geometry import Polygon
from shapely.ops import unary_union

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import ttProgram

RADIUS = 12          # corner radius in font units (1000 UPM) — "very little"
SAMPLE = 7.0         # max chord length when flattening curves
SIMPLIFY = 0.7       # final point-thinning tolerance
QS = 6               # arc smoothness of the rounded corners


def flatten_segments(rec):
    """RecordingPen value -> list of closed point-loops."""
    contours, cur, start = [], [], None
    for op, args in rec:
        if op == 'moveTo':
            cur = [args[0]]
            start = args[0]
        elif op == 'lineTo':
            cur.append(args[0])
        elif op == 'qCurveTo':
            pts = list(args)
            if pts[-1] is None:          # TrueType all-off-curve contour
                pts[-1] = start
            p0 = cur[-1]
            # expand implied on-curve midpoints
            offs = pts[:-1]
            segs = []
            if len(offs) <= 1:
                segs.append((p0, offs[0] if offs else p0, pts[-1]))
            else:
                prev = p0
                for i in range(len(offs) - 1):
                    mid = ((offs[i][0] + offs[i + 1][0]) / 2,
                           (offs[i][1] + offs[i + 1][1]) / 2)
                    segs.append((prev, offs[i], mid))
                    prev = mid
                segs.append((prev, offs[-1], pts[-1]))
            for a, b, c in segs:
                length = (math.dist(a, b) + math.dist(b, c))
                n = max(2, int(length / SAMPLE))
                for i in range(1, n + 1):
                    t = i / n
                    mt = 1 - t
                    cur.append((mt * mt * a[0] + 2 * mt * t * b[0] + t * t * c[0],
                                mt * mt * a[1] + 2 * mt * t * b[1] + t * t * c[1]))
        elif op == 'curveTo':            # cubic (rare in TTF): sample
            p0 = cur[-1]
            b, c, d = args
            length = math.dist(p0, b) + math.dist(b, c) + math.dist(c, d)
            n = max(3, int(length / SAMPLE))
            for i in range(1, n + 1):
                t = i / n
                mt = 1 - t
                cur.append((mt**3 * p0[0] + 3 * mt * mt * t * b[0] + 3 * mt * t * t * c[0] + t**3 * d[0],
                            mt**3 * p0[1] + 3 * mt * mt * t * b[1] + 3 * mt * t * t * c[1] + t**3 * d[1]))
        elif op == 'closePath':
            if len(cur) >= 3:
                contours.append(cur)
            cur = []
    return contours


def signed_area(pts):
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return s / 2


def to_geometry(contours):
    outers, holes = [], []
    for c in contours:
        p = Polygon(c)
        if not p.is_valid:
            p = p.buffer(0)
        if p.is_empty:
            continue
        # TrueType y-up: outer contours wind CW (negative shoelace area)
        (holes if signed_area(c) > 0 else outers).append(p)
    if not outers:
        return None
    g = unary_union(outers)
    if holes:
        g = g.difference(unary_union(holes))
    return g


def round_geometry(g, r):
    out = (g.buffer(r, quad_segs=QS, join_style=1)
            .buffer(-2 * r, quad_segs=QS, join_style=1)
            .buffer(r, quad_segs=QS, join_style=1)
            .simplify(SIMPLIFY))
    return out


def geometry_to_glyph(g):
    from shapely.geometry.polygon import orient
    pen = TTGlyphPen(None)
    polys = [g] if g.geom_type == 'Polygon' else list(g.geoms)
    for p in polys:
        if p.is_empty or p.area < 10:
            continue
        p = orient(p, sign=-1.0)   # exterior CW, holes CCW (TT y-up)
        rings = [list(p.exterior.coords)[:-1]] + \
                [list(h.coords)[:-1] for h in p.interiors]
        for ring in rings:
            pen.moveTo((round(ring[0][0]), round(ring[0][1])))
            for x, y in ring[1:]:
                pen.lineTo((round(x), round(y)))
            pen.closePath()
    return pen.glyph()


def process(path_in, path_out, new_family, radius=RADIUS):
    font = TTFont(path_in)
    glyf = font['glyf']
    glyph_set = font.getGlyphSet()
    skipped, done = [], 0

    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.isComposite():
            # children get rounded; just drop stale composite instructions
            if hasattr(glyph, 'program'):
                glyph.program = ttProgram.Program()
            continue
        if glyph.numberOfContours <= 0:
            continue
        rec = RecordingPen()
        glyph_set[name].draw(rec)
        contours = flatten_segments(rec.value)
        g = to_geometry(contours)
        if g is None or g.is_empty:
            skipped.append(name)
            continue
        rounded = round_geometry(g, radius)
        if rounded.is_empty or rounded.area < g.area * 0.75:
            skipped.append(name)     # feature too thin — keep original
            continue
        glyf[name] = geometry_to_glyph(rounded)
        done += 1

    # names: swap family; RETAIN original copyright + OFL license (required
    # by the OFL) and add our modification statement on top.
    name_tab = font['name']
    for rec in name_tab.names:
        if rec.nameID in (1, 3, 4, 6, 16, 18, 21):
            s = rec.toUnicode()
            if 'Montserrat' in s:
                repl = new_family.replace(' ', '') if rec.nameID == 6 else new_family
                rec.string = s.replace('Montserrat', repl)
        elif rec.nameID == 0:
            rec.string = (rec.toUnicode() +
                          ' | %s: corner-rounded derivative, '
                          'Copyright 2026 Miraz Mullick, licensed under the '
                          'SIL Open Font License 1.1' % new_family)
        elif rec.nameID == 5:
            rec.string = rec.toUnicode() + '; corner-rounded derivative of Montserrat'

    font.save(path_out)
    return done, skipped


if __name__ == '__main__':
    src, dst, fam = sys.argv[1], sys.argv[2], sys.argv[3]
    r = float(sys.argv[4]) if len(sys.argv) > 4 else RADIUS
    done, skipped = process(src, dst, fam, r)
    print(f'{src} -> {dst}: rounded {done} glyphs, kept original for {len(skipped)}')
    if skipped:
        print('  kept:', ' '.join(skipped[:20]), '...' if len(skipped) > 20 else '')

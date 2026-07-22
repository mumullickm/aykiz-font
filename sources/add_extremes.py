"""Insert on-curve points at quadratic extrema in built TTFs (exact split).

ufo2ft 3.6.x no longer bundles the AddExtremes filter Montserrat's source
declares, so a local build lacks the extrema Montserrat's own build adds. This
post-pass rebuilds each simple glyph, splitting any quadratic segment that
crosses an x- or y-extreme (beyond a small tolerance) at that extreme, matching
the quality of the official Montserrat binaries. Composite glyphs (accents) are
left alone; their bases are fixed. Exact de Casteljau split, so outlines are
geometrically unchanged.
"""
import glob
import os
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen

TOL = 1.0  # only split when the extreme deviates from both endpoints by > TOL units


def _extrema_ts(a, b, c):
    ts = []
    for a0, a1, a2 in ((a[0], b[0], c[0]), (a[1], b[1], c[1])):
        d = a0 - 2 * a1 + a2
        if abs(d) > 1e-9:
            t = (a0 - a1) / d
            if 1e-4 < t < 1 - 1e-4:
                ts.append(t)
    return sorted(set(round(t, 6) for t in ts))


def _lerp(p, q, t):
    return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)


def _split_quad(a, b, c, t):
    p01 = _lerp(a, b, t)
    p12 = _lerp(b, c, t)
    m = _lerp(p01, p12, t)
    return (a, p01, m), (m, p12, c)


def _needs_split(a, b, c, t):
    # split point coordinate; deviation from endpoints per axis
    p01 = _lerp(a, b, t); p12 = _lerp(b, c, t); m = _lerp(p01, p12, t)
    for ax in (0, 1):
        lo, hi = min(a[ax], c[ax]), max(a[ax], c[ax])
        if m[ax] < lo - TOL or m[ax] > hi + TOL:
            return True
    return False


def _split_all(a, b, c):
    """Split quad (a,b,c) at all needed extrema; return list of (ctrl,end)."""
    out = []
    stack = [(a, b, c)]
    while stack:
        qa, qb, qc = stack.pop(0)
        ts = _extrema_ts(qa, qb, qc)
        did = False
        for t in ts:
            if _needs_split(qa, qb, qc, t):
                left, right = _split_quad(qa, qb, qc, t)
                stack.insert(0, right)
                stack.insert(0, left)
                did = True
                break
        if not did:
            out.append((qb, qc))
    return out


def _expand_qcurve(cur, pts, start):
    """Expand a TrueType qCurveTo super-segment into simple (a,b,c) quads."""
    offs = list(pts[:-1])
    end = pts[-1] if pts[-1] is not None else start
    quads = []
    prev = cur
    for i, off in enumerate(offs):
        if i < len(offs) - 1:
            nxt = offs[i + 1]
            mid = ((off[0] + nxt[0]) / 2, (off[1] + nxt[1]) / 2)
            quads.append((prev, off, mid))
            prev = mid
        else:
            quads.append((prev, off, end))
            prev = end
    return quads, end


def fix_glyph(rec_value, start_default=(0, 0)):
    pen = TTGlyphPen(None)
    cur = None
    start = None
    for op, pts in rec_value:
        if op == "moveTo":
            cur = pts[0]; start = pts[0]; pen.moveTo(cur)
        elif op == "lineTo":
            cur = pts[0]; pen.lineTo(cur)
        elif op == "curveTo":
            for p in pts:
                pass
            pen.curveTo(*pts); cur = pts[-1]
        elif op == "qCurveTo":
            quads, end = _expand_qcurve(cur, pts, start)
            for a, b, c in quads:
                for ctrl, e in _split_all(a, b, c):
                    pen.qCurveTo(ctrl, e)
            cur = end
        elif op == "closePath":
            pen.closePath(); cur = start
        elif op == "endPath":
            pen.endPath()
    return pen.glyph()


def process(path):
    f = TTFont(path)
    glyf = f["glyf"]
    gs = f.getGlyphSet()
    fixed = 0
    for name in f.getGlyphOrder():
        g = glyf[name]
        if g.isComposite() or g.numberOfContours == 0:
            continue
        rec = RecordingPen()
        gs[name].draw(rec)
        glyf[name] = fix_glyph(rec.value)
        fixed += 1
    f.save(path)
    return fixed


if __name__ == "__main__":
    for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.ttf"))):
        n = process(p)
        print(f"{os.path.basename(p):28s} extrema-fixed {n} simple glyphs")

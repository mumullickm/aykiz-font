"""Aykiz corner rounding v2 — curve-preserving.

v1 flattened outlines to polylines (correctly criticized in review: no true
curves in the output). v2 never flattens: it keeps every original quadratic
bezier untouched, finds real corners by tangent discontinuity, trims the two
adjacent segments back by the radius, and bridges each corner with a single
genuine quadratic whose control point is the original corner. Straight edges
stay lines, curves stay curves, every rounded corner is one real curve.
"""
import math
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables import ttProgram
from fontTools.misc.bezierTools import splitQuadraticAtT, calcQuadraticArcLength

CORNER_ANGLE = 22          # degrees of tangent change that counts as a corner
MAX_TRIM_FRACTION = 0.42   # never consume more than this much of a segment per end


# ---------------------------------------------------------------- segments
# segment = ('line', p0, p1) | ('quad', p0, c, p1)

def contours_from_glyph(glyph_set, name):
    rec = RecordingPen()
    glyph_set[name].draw(rec)
    contours, cur, start = [], [], None
    for op, args in rec.value:
        if op == 'moveTo':
            start = args[0]
            cur = []
            last = start
        elif op == 'lineTo':
            cur.append(('line', last, args[0]))
            last = args[0]
        elif op == 'qCurveTo':
            pts = list(args)
            if pts[-1] is None:              # all-off-curve TrueType contour
                # implied start = midpoint of last off and first off
                first_off = pts[0]
                implied_start = ((pts[-2][0] + start[0]) / 2, (pts[-2][1] + start[1]) / 2) \
                    if False else None
                # fontTools emits moveTo at implied on-curve already for None-contours
                pts[-1] = start
            offs, on = pts[:-1], pts[-1]
            if not offs:
                cur.append(('line', last, on))
            elif len(offs) == 1:
                cur.append(('quad', last, offs[0], on))
            else:
                prev = last
                for i in range(len(offs) - 1):
                    mid = ((offs[i][0] + offs[i + 1][0]) / 2,
                           (offs[i][1] + offs[i + 1][1]) / 2)
                    cur.append(('quad', prev, offs[i], mid))
                    prev = mid
                cur.append(('quad', prev, offs[-1], on))
            last = on
        elif op == 'curveTo':
            raise ValueError('cubic in TTF unexpected')
        elif op == 'closePath':
            if last != start:
                cur.append(('line', last, start))
            if cur:
                contours.append(cur)
            cur = []
    return contours


def seg_length(s):
    if s[0] == 'line':
        return math.dist(s[1], s[2])
    return calcQuadraticArcLength(s[1], s[2], s[3])


def tangent_out(s):
    if s[0] == 'line':
        v = (s[2][0] - s[1][0], s[2][1] - s[1][1])
    else:
        v = (s[3][0] - s[2][0], s[3][1] - s[2][1])
        if v == (0, 0):
            v = (s[3][0] - s[1][0], s[3][1] - s[1][1])
    return v


def tangent_in(s):
    if s[0] == 'line':
        v = (s[2][0] - s[1][0], s[2][1] - s[1][1])
    else:
        v = (s[2][0] - s[1][0], s[2][1] - s[1][1])
        if v == (0, 0):
            v = (s[3][0] - s[1][0], s[3][1] - s[1][1])
    return v


def angle_between(v1, v2):
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def trim_end(s, d):
    """Cut length d off the end of a segment."""
    L = seg_length(s)
    if L <= 1e-6 or d <= 0:
        return s
    t = max(0.0, 1.0 - d / L)
    if s[0] == 'line':
        p = (s[1][0] + (s[2][0] - s[1][0]) * t, s[1][1] + (s[2][1] - s[1][1]) * t)
        return ('line', s[1], p)
    first, _ = splitQuadraticAtT(s[1], s[2], s[3], t)
    return ('quad', first[0], first[1], first[2])


def trim_start(s, d):
    L = seg_length(s)
    if L <= 1e-6 or d <= 0:
        return s
    t = min(1.0, d / L)
    if s[0] == 'line':
        p = (s[1][0] + (s[2][0] - s[1][0]) * t, s[1][1] + (s[2][1] - s[1][1]) * t)
        return ('line', p, s[2])
    _, second = splitQuadraticAtT(s[1], s[2], s[3], t)
    return ('quad', second[0], second[1], second[2])


def round_contour(segs, radius):
    n = len(segs)
    if n < 2:
        return segs
    # decide which junctions are corners; junction i is between segs[i] and segs[(i+1)%n]
    corner = [False] * n
    for i in range(n):
        j = (i + 1) % n
        ang = angle_between(tangent_out(segs[i]), tangent_in(segs[j]))
        if ang > CORNER_ANGLE:
            corner[i] = True
    if not any(corner):
        return segs
    # per-junction trim, clamped so a segment never loses too much of itself
    lens = [seg_length(s) for s in segs]
    trim = [0.0] * n
    for i in range(n):
        if corner[i]:
            j = (i + 1) % n
            trim[i] = min(radius, lens[i] * MAX_TRIM_FRACTION, lens[j] * MAX_TRIM_FRACTION)
    out = []
    for i in range(n):
        s = segs[i]
        prev_j = (i - 1) % n
        s = trim_start(s, trim[prev_j] if corner[prev_j] else 0.0)
        s = trim_end(s, trim[i] if corner[i] else 0.0)
        out.append(s)
        if corner[i] and trim[i] > 0.35:
            j = (i + 1) % n
            corner_pt = segs[i][-1]           # original junction point
            start_pt = out[-1][-1]            # trimmed end of current
            nxt = trim_start(segs[j], trim[i])
            end_pt = nxt[1]
            out.append(('quad', start_pt, corner_pt, end_pt))
    # stitch: recompute start points so the contour is exactly closed
    stitched = []
    for k, s in enumerate(out):
        prev_end = out[k - 1][-1]
        if s[0] == 'line':
            stitched.append(('line', prev_end, s[2]))
        else:
            stitched.append(('quad', prev_end, s[2], s[3]))
    return stitched


def contour_to_pen(segs, pen):
    r = lambda p: (round(p[0]), round(p[1]))
    start = r(segs[0][1])
    pen.moveTo(start)
    for s in segs:
        if s[0] == 'line':
            if r(s[2]) != r(s[1]):
                pen.lineTo(r(s[2]))
        else:
            pen.qCurveTo(r(s[2]), r(s[3]))
    pen.closePath()


# ---------------------------------------------------------------- pipeline

def process(path_in, path_out, new_family, radius):
    font = TTFont(path_in)
    glyf = font['glyf']
    glyph_set = font.getGlyphSet()
    done = 0
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.isComposite():
            if hasattr(glyph, 'program'):
                glyph.program = ttProgram.Program()
            continue
        if glyph.numberOfContours <= 0:
            continue
        try:
            contours = contours_from_glyph(glyph_set, name)
        except ValueError:
            continue
        pen = TTGlyphPen(None)
        for c in contours:
            contour_to_pen(round_contour(c, radius), pen)
        glyf[name] = pen.glyph()
        done += 1

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
            rec.string = (rec.toUnicode() +
                          '; corner-rounded derivative of Montserrat (v1.1 curve-preserving)')
    font['head'].fontRevision = 1.1
    font.save(path_out)
    return done


if __name__ == '__main__':
    src, dst, fam = sys.argv[1], sys.argv[2], sys.argv[3]
    r = float(sys.argv[4]) if len(sys.argv) > 4 else 12
    done = process(src, dst, fam, r)
    print(f'{src} -> {dst}: processed {done} glyphs (curve-preserving, r={r})')

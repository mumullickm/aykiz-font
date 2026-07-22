"""Aykiz corner-rounding filter (interpolation-safe).

Fillets sharp *line-to-line* corners on UFO master outlines with true circular
cubic Bezier arcs. Existing curves, smooth (tangent) joins, and components are
untouched, so bowls stay bowls and only rectilinear corners soften.

Interpolation safety: the DECISION of which corners to fillet is taken ONCE
from a reference master (per glyph/contour/anchor) using a structural test
(line->line, not smooth) plus a generous angle test that rejects the collinear
mid-stem points Montserrat inserts for interpolation control. That identical
anchor set is then applied to every master, so all masters keep matching point
counts/types and remain compatible. Only the fillet radius (hence the
coordinates) varies per weight.

Fillet geometry for corner P with prev anchor A, next anchor B:
  dir_in=unit(P-A), dir_out=unit(B-P), beta=angle(dir_in,dir_out)
  d=r*tan(beta/2) clamped to 45% of each edge; ratio=(4/3)tan(beta/4)/tan(beta/2)
  line->T_in=P-d*dir_in ; cubic(C1,C2)->T_out=P+d*dir_out
  C1=P-d*(1-ratio)*dir_in ; C2=P+d*(1-ratio)*dir_out
"""
import math

import ufoLib2

MIN_TURN_DEG = 15.0     # reject near-collinear mid-stem points (real corners are >~30 deg)
EDGE_CLAMP = 0.45


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    if n == 0:
        return 0.0, 0.0, 0.0
    return dx / n, dy / n, n


def _anchor_indices(points):
    return [i for i, p in enumerate(points) if p.type is not None]


def _corner_turn(points, onc, k):
    """Turn angle (radians) at on-curve anchor order k, or None if not a line-line
    non-smooth corner."""
    p = points[onc[k]]
    if p.type != "line" or p.smooth:
        return None
    nxt = points[onc[(k + 1) % len(onc)]]
    if nxt.type != "line":
        return None
    P = (p.x, p.y)
    A = (points[onc[(k - 1) % len(onc)]].x, points[onc[(k - 1) % len(onc)]].y)
    B = (points[onc[(k + 1) % len(onc)]].x, points[onc[(k + 1) % len(onc)]].y)
    ix, iy, li = _unit(P[0] - A[0], P[1] - A[1])
    ox, oy, lo = _unit(B[0] - P[0], B[1] - P[1])
    if li == 0 or lo == 0:
        return None
    cosb = max(-1.0, min(1.0, ix * ox + iy * oy))
    return math.acos(cosb)


def classify_glyph(glyph):
    """Return {contour_index: set(anchor_order)} of corners to fillet, from this
    (reference) glyph."""
    decisions = {}
    for ci, c in enumerate(glyph.contours):
        pts = list(c)
        onc = _anchor_indices(pts)
        if len(onc) < 3:
            continue
        keep = set()
        for k in range(len(onc)):
            beta = _corner_turn(pts, onc, k)
            if beta is not None and math.degrees(beta) >= MIN_TURN_DEG:
                keep.add(k)
        if keep:
            decisions[ci] = keep
    return decisions


def _apply_contour(points, fillet_orders, radius):
    onc = _anchor_indices(points)
    pos = {idx: k for k, idx in enumerate(onc)}
    anchor_xy = [(points[i].x, points[i].y) for i in onc]
    repl = {}
    for k in fillet_orders:
        if k >= len(onc):
            continue
        idx = onc[k]
        P = anchor_xy[k]
        A = anchor_xy[(k - 1) % len(onc)]
        B = anchor_xy[(k + 1) % len(onc)]
        ix, iy, li = _unit(P[0] - A[0], P[1] - A[1])
        ox, oy, lo = _unit(B[0] - P[0], B[1] - P[1])
        if li == 0 or lo == 0:
            # degenerate in this master: emit a zero fillet at P to keep counts equal
            repl[idx] = (P, P, P, P)
            continue
        cosb = max(-1.0, min(1.0, ix * ox + iy * oy))
        beta = math.acos(cosb)
        if beta < 1e-4:
            repl[idx] = (P, P, P, P)
            continue
        d = radius * math.tan(beta / 2.0)
        d = min(d, EDGE_CLAMP * li, EDGE_CLAMP * lo)
        ratio = (4.0 / 3.0) * math.tan(beta / 4.0) / math.tan(beta / 2.0)
        T_in = (P[0] - d * ix, P[1] - d * iy)
        T_out = (P[0] + d * ox, P[1] + d * oy)
        C1 = (P[0] - d * (1 - ratio) * ix, P[1] - d * (1 - ratio) * iy)
        C2 = (P[0] + d * (1 - ratio) * ox, P[1] + d * (1 - ratio) * oy)
        repl[idx] = (T_in, C1, C2, T_out)

    out = []
    for i, p in enumerate(points):
        if i in repl:
            T_in, C1, C2, T_out = repl[i]
            out.append((T_in, "line", False))
            out.append((C1, None, False))
            out.append((C2, None, False))
            out.append((T_out, "curve", False))
        else:
            out.append(((p.x, p.y), p.type, p.smooth))
    return out


def apply_glyph(glyph, decisions, radius):
    if not len(glyph.contours):
        return
    new_contours = []
    for ci, c in enumerate(glyph.contours):
        pts = list(c)
        orders = decisions.get(ci, set())
        new_contours.append(_apply_contour(pts, orders, radius))
    glyph.clearContours()
    pen = glyph.getPointPen()
    for npts in new_contours:
        pen.beginPath()
        for xy, seg, smooth in npts:
            pen.addPoint(xy, segmentType=seg, smooth=smooth)
        pen.endPath()


def round_masters(master_paths, reference_index, radius_map):
    """Round a compatible set of masters with a shared per-glyph decision.

    master_paths: list of UFO paths (all point-compatible).
    reference_index: index into master_paths used to classify corners.
    radius_map: {ufo_path: radius}.
    """
    fonts = [ufoLib2.Font.open(p) for p in master_paths]
    ref = fonts[reference_index]
    # classify from reference for every glyph that has contours
    glyph_decisions = {}
    for g in ref:
        if len(g.contours):
            d = classify_glyph(g)
            if d:
                glyph_decisions[g.name] = d
    total = 0
    for path, font in zip(master_paths, fonts):
        r = radius_map[path]
        for name, decisions in glyph_decisions.items():
            if name in font:
                apply_glyph(font[name], decisions, r)
                total += sum(len(s) for s in decisions.values())
        font.save(path, overwrite=True)
    return glyph_decisions

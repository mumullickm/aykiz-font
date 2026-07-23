"""Aykiz corner-rounding filter (interpolation-safe).

Fillets sharp *terminal* corners on UFO master outlines with true circular
cubic Bezier arcs, while leaving stroke overlaps/crossings crisp. Existing
curves, smooth (tangent) joins, and components are untouched.

Two problems the earlier line-to-line-only filter got wrong (GF review round 2,
issue #10715):

  1. Terminals where a *curve* meets the flat stroke end (C G J Q S, etc.) were
     skipped because only line->line corners were considered. This version also
     rounds curve->line and line->curve corners, trimming the curved side ON the
     original outline via a de Casteljau split so the bowl is not distorted.

  2. Interior stroke crossings/overlaps (the loops inside `X`, the crossbar of
     `e`) were being rounded, which a designer keeps sharp and which kink at
     Black. These are detected structurally: an overlap corner sits very close
     to another (non-incident) edge of the same glyph. Corners whose nearest
     non-incident edge is closer than PROXIMITY_FACTOR * radius are left sharp.

Interpolation safety: the DECISION of which corners to fillet is taken ONCE from
a reference master (per glyph/contour/anchor). That identical anchor set is then
applied to every master, so all masters keep matching point counts/types and
stay compatible. Only the fillet coordinates vary per weight.
"""
import math

import ufoLib2

MIN_TURN_DEG = 15.0        # reject near-collinear mid-stem points
EDGE_CLAMP = 0.45          # never eat more than 45% of an edge / curve chord
PROXIMITY_FACTOR = 2.2     # skip a corner if nearest non-incident edge is
                           # closer than PROXIMITY_FACTOR * radius (overlap test)


def _unit(dx, dy):
    n = math.hypot(dx, dy)
    if n == 0:
        return 0.0, 0.0, 0.0
    return dx / n, dy / n, n


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------
def _dist_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _anchor_polys(glyph):
    """On-curve-anchor polygon for every contour (coarse outline, used only for
    the proximity/overlap test)."""
    polys = []
    for c in glyph.contours:
        polys.append([(p.x, p.y) for p in c if p.type is not None])
    return polys


def _min_gap(P, polys, own_ci, own_anchor_k):
    """Distance from anchor P (order own_anchor_k in contour own_ci) to the
    nearest edge that is NOT incident to P."""
    best = 1e18
    for ci, poly in enumerate(polys):
        n = len(poly)
        if n < 2:
            continue
        for j in range(n):
            if ci == own_ci and (j == own_anchor_k or (j + 1) % n == own_anchor_k):
                continue  # edge touches P
            a = poly[j]
            b = poly[(j + 1) % n]
            d = _dist_pt_seg(P[0], P[1], a[0], a[1], b[0], b[1])
            if d < best:
                best = d
    return best


def _cubic_point(p0, p1, p2, p3, t):
    mt = 1 - t
    a = mt * mt * mt
    b = 3 * mt * mt * t
    c = 3 * mt * t * t
    d = t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def _split_cubic(p0, p1, p2, p3, t):
    """de Casteljau split -> (left ctrls, split point, right ctrls)."""
    def lerp(a, b, u):
        return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
    ab = lerp(p0, p1, t); bc = lerp(p1, p2, t); cd = lerp(p2, p3, t)
    abc = lerp(ab, bc, t); bcd = lerp(bc, cd, t)
    m = lerp(abc, bcd, t)
    return (ab, abc), m, (bcd, cd)   # left=(p0,ab,abc,m), right=(m,bcd,cd,p3)


def _t_at_distance_from_end(p0, p1, p2, p3, dist, from_start):
    """Parameter t where the cubic is Euclidean-distance `dist` from its start
    (from_start=True, anchor at t=0) or end (t=1). Bisection; monotonic near the
    relevant end for the small distances used here."""
    anchor = p0 if from_start else p3
    lo, hi = (0.0, 1.0)
    # search t in the half nearest the anchor
    if from_start:
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            pt = _cubic_point(p0, p1, p2, p3, mid)
            if math.hypot(pt[0] - anchor[0], pt[1] - anchor[1]) < dist:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    else:
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            pt = _cubic_point(p0, p1, p2, p3, mid)
            if math.hypot(pt[0] - anchor[0], pt[1] - anchor[1]) < dist:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2


# ---------------------------------------------------------------------------
# corner model
# ---------------------------------------------------------------------------
class _Corner:
    """A rounding candidate at on-curve anchor of order k in a contour."""
    __slots__ = ("k", "idx", "in_type", "out_type", "P", "dir_in", "dir_out",
                 "len_in", "len_out", "turn")


def _corners(points):
    """Yield structural info for every non-smooth on-curve corner. Direction is
    the true tangent (uses the adjacent control point on a curved side)."""
    n = len(points)
    onc = [i for i, p in enumerate(points) if p.type is not None]
    m = len(onc)
    out = []
    for k in range(m):
        i = onc[k]
        p = points[i]
        if p.smooth or p.type == "move":
            continue
        in_type = p.type                              # segment arriving at P
        nxt_anchor = points[onc[(k + 1) % m]]
        out_type = nxt_anchor.type                    # segment leaving P
        # neighbour points that define the tangents at P
        prev_pt = points[(i - 1) % n]                 # control if in curve, else anchor
        next_pt = points[(i + 1) % n]                 # control if out curve, else anchor
        P = (p.x, p.y)
        ix, iy, li = _unit(P[0] - prev_pt.x, P[1] - prev_pt.y)
        ox, oy, lo = _unit(next_pt.x - P[0], next_pt.y - P[1])
        if li == 0 or lo == 0:
            continue
        cosb = max(-1.0, min(1.0, ix * ox + iy * oy))
        turn = math.degrees(math.acos(cosb))
        if turn < MIN_TURN_DEG:
            continue
        c = _Corner()
        c.k, c.idx = k, i
        c.in_type, c.out_type = in_type, out_type
        c.P = P
        c.dir_in, c.dir_out = (ix, iy), (ox, oy)
        c.len_in, c.len_out = li, lo
        c.turn = turn
        out.append(c)
    return out


def classify_glyph(glyph, ref_radius):
    """Return {contour_index: set(anchor_order k)} to fillet, decided on this
    reference glyph. Overlap corners (near another edge) are excluded."""
    polys = _anchor_polys(glyph)
    decisions = {}
    for ci, c in enumerate(glyph.contours):
        pts = list(c)
        onc = [i for i, p in enumerate(pts) if p.type is not None]
        if len(onc) < 3:
            continue
        keep = set()
        for cor in _corners(pts):
            gap = _min_gap(cor.P, polys, ci, cor.k)
            if gap < PROXIMITY_FACTOR * ref_radius:
                continue  # stroke overlap / crossing -> keep sharp
            keep.add(cor.k)
        if keep:
            decisions[ci] = keep
    return decisions


# ---------------------------------------------------------------------------
# application
# ---------------------------------------------------------------------------
def _apply_contour(points, fillet_orders, radius):
    n = len(points)
    onc = [i for i, p in enumerate(points) if p.type is not None]
    m = len(onc)
    corners = {c.k: c for c in _corners(points)}

    # Per-anchor edit plan. Each on-curve index may get: its incoming curve
    # trimmed (new ctrls + endpoint), and/or a fillet inserted after it, and/or
    # its outgoing curve trimmed (new start ctrls).
    trim_in = {}     # idx -> (new_c1, new_c2, new_endpoint)   (only for curve-in)
    fillet = {}      # idx -> (T_in, C1, C2, T_out)
    trim_out = {}    # idx -> (new_o1, new_o2)                 (only for curve-out)

    for k in fillet_orders:
        if k >= m:
            continue
        i = onc[k]
        P = (points[i].x, points[i].y)
        c = corners.get(k)
        # Degenerate in THIS master (corner too shallow / zero-length edge): emit
        # a zero fillet so the point-type sequence stays identical to the masters
        # where the fillet is real. Interpolation needs matching counts, not
        # matching coordinates.
        if c is None:
            fillet[i] = (P, P, P, P)
            continue
        ix, iy = c.dir_in
        ox, oy = c.dir_out
        beta = math.radians(c.turn)
        d = radius * math.tan(beta / 2.0)
        d = min(d, EDGE_CLAMP * c.len_in, EDGE_CLAMP * c.len_out)
        if beta < 1e-4 or d <= 0:
            fillet[i] = (P, P, P, P)
            continue

        # --- incoming side: find the tangent point T_in that lies ON the outline
        if c.in_type == "line":
            T_in = (P[0] - d * ix, P[1] - d * iy)
            din = (ix, iy)
        else:  # curve arriving at P: split the cubic d units back from P
            p3 = P
            p2 = (points[(i - 1) % n].x, points[(i - 1) % n].y)
            p1 = (points[(i - 2) % n].x, points[(i - 2) % n].y)
            p0 = (points[onc[(k - 1) % m]].x, points[onc[(k - 1) % m]].y)
            t = _t_at_distance_from_end(p0, p1, p2, p3, d, from_start=False)
            left, mpt, _ = _split_cubic(p0, p1, p2, p3, t)
            T_in = mpt
            trim_in[i] = (left[0], left[1], mpt)           # p0,new_c1,new_c2,T_in
            tx, ty, tl = _unit(mpt[0] - left[1][0], mpt[1] - left[1][1])
            din = (tx, ty) if tl else (ix, iy)

        # --- outgoing side
        if c.out_type == "line":
            T_out = (P[0] + d * ox, P[1] + d * oy)
            dout = (ox, oy)
        else:  # curve leaving P: split d units forward from P
            o0 = P
            o1 = (points[(i + 1) % n].x, points[(i + 1) % n].y)
            o2 = (points[(i + 2) % n].x, points[(i + 2) % n].y)
            nxt_anchor_idx = onc[(k + 1) % m]
            o3 = (points[nxt_anchor_idx].x, points[nxt_anchor_idx].y)
            t2 = _t_at_distance_from_end(o0, o1, o2, o3, d, from_start=True)
            _, mpt2, right = _split_cubic(o0, o1, o2, o3, t2)
            T_out = mpt2
            trim_out[i] = (right[0], right[1])             # new start ctrls after T_out
            sx, sy, sl = _unit(right[0][0] - mpt2[0], right[0][1] - mpt2[1])
            dout = (sx, sy) if sl else (ox, oy)

        # --- fillet arc between T_in and T_out, tangent to both directions.
        # Cubic handle length for a circular arc: h = d * (4/3)tan(b/4)/tan(b/2).
        ratio = (4.0 / 3.0) * math.tan(beta / 4.0) / math.tan(beta / 2.0)
        ctrl_len = d * ratio
        C1 = (T_in[0] + ctrl_len * din[0], T_in[1] + ctrl_len * din[1])
        C2 = (T_out[0] - ctrl_len * dout[0], T_out[1] - ctrl_len * dout[1])
        fillet[i] = (T_in, C1, C2, T_out)

    # ---- rebuild the point list.
    # Substitute trimmed control points / endpoints by index, then splice in the
    # fillet segments right after each filleted anchor.
    off_repl = {}
    end_repl = {}
    start_repl = {}
    for i, (c1, c2, end) in trim_in.items():
        off_repl[(i - 2) % n] = c1
        off_repl[(i - 1) % n] = c2
        end_repl[i] = end
    for i, (o1, o2) in trim_out.items():
        off_repl[(i + 1) % n] = o1
        off_repl[(i + 2) % n] = o2

    seq = []
    for i, p in enumerate(points):
        x, y, seg, smooth = p.x, p.y, p.type, p.smooth
        if i in off_repl:
            x, y = off_repl[i]
        if i in end_repl:
            x, y = end_repl[i]
        seq.append([(x, y), seg, smooth, i])

    # now insert fillets right after each filleted anchor
    final = []
    for (xy, seg, smooth, i) in seq:
        if i in fillet:
            T_in, C1, C2, T_out = fillet[i]
            # the anchor i is replaced by T_in (as the end of the incoming seg),
            # keeping its original segment type (line or curve)
            final.append((T_in, seg, False))
            final.append((C1, None, False))
            final.append((C2, None, False))
            final.append((T_out, "curve", False))
        else:
            final.append((xy, seg, smooth))
    return final


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

    Decisions (incl. the overlap test) are taken on the reference master using
    its radius, then applied to every master at that master's radius.
    """
    fonts = [ufoLib2.Font.open(p) for p in master_paths]
    ref = fonts[reference_index]
    ref_radius = radius_map[master_paths[reference_index]]
    glyph_decisions = {}
    for g in ref:
        if len(g.contours):
            d = classify_glyph(g, ref_radius)
            if d:
                glyph_decisions[g.name] = d
    for path, font in zip(master_paths, fonts):
        r = radius_map[path]
        for name, decisions in glyph_decisions.items():
            if name in font:
                apply_glyph(font[name], decisions, r)
        font.save(path, overwrite=True)
    return glyph_decisions

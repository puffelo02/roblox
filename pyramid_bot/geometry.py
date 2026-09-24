"""Pyramid geometry, worked out from the block counter.

A pyramid of 171,700 blocks is 100x100 at the base and every layer is one block
smaller on each side:  100^2 + 98^2 + 96^2 + ... + 2^2 = 171,700  (50 layers).

Coordinates are in blocks, seen from where the bot anchors: x runs along the
base wall it faced (0 = left corner, base = right corner), y goes into the
pyramid (0 = that wall). Layer k (1 = bottom) covers [k-1, base-(k-1)] on both axes.
"""


def base_size(total):
    """Base width for a pyramid of `total` blocks, or None if it isn't a step pyramid."""
    for m in range(1, 500):
        even = 4 * m * (m + 1) * (2 * m + 1) // 6   # 2^2 + 4^2 + ... + (2m)^2
        odd = m * (2 * m - 1) * (2 * m + 1) // 3    # 1^2 + 3^2 + ... + (2m-1)^2
        if even == total:
            return 2 * m
        if odd == total:
            return 2 * m - 1
        if min(even, odd) > total:
            return None
    return None


def layer_info(count, base):
    """(completed layers, side of the layer being built, blocks already in it)."""
    done = 0
    n = 0
    side = base
    while side > 0 and done + side * side <= count:
        done += side * side
        n += 1
        side -= 2
    return n, side, count - done


def layer_bounds(completed, base):
    """(lo, hi) of the layer being built when `completed` layers are finished."""
    return completed, base - completed


def spiral(lo, hi, lane, corner, first_axis, edge=None):
    """Inward square spiral inside [lo, hi] x [lo, hi], `lane` blocks between passes.

    corner: (cx, cy), each 0 (low side) or 1 (high side): where it starts.
    first_axis: "x" or "y": which way the first leg goes.
    edge: distance of the outermost lap from the layer edge (default lane / 2).
    Returns the list of waypoints (x, y), corners of the path, outside first.
    """
    edge = lane / 2 if edge is None else edge
    a = lo + edge
    b = hi - edge
    if b <= a:
        mid = (lo + hi) / 2
        return [(mid, mid)]
    x = a if corner[0] == 0 else b
    y = a if corner[1] == 0 else b
    sx = 1 if corner[0] == 0 else -1  # direction toward the far x side
    sy = 1 if corner[1] == 0 else -1
    if first_axis == "y":
        dirs = [(0, sy), (sx, 0), (0, -sy), (-sx, 0)]
    else:
        dirs = [(sx, 0), (0, sy), (-sx, 0), (0, -sy)]
    ext = b - a
    legs = [ext, ext, ext]
    k = 1
    while ext - k * lane > 0:
        legs += [ext - k * lane, ext - k * lane]
        k += 1
    pts = [(x, y)]
    for i, length in enumerate(legs):
        dx, dy = dirs[i % 4]
        x += dx * length
        y += dy * length
        pts.append((x, y))
    return pts


def all_spirals(lo, hi, lane, edge=None):
    """Every inward variant (4 corners x 2 first directions)."""
    return [
        spiral(lo, hi, lane, (cx, cy), axis, edge)
        for cx in (0, 1)
        for cy in (0, 1)
        for axis in ("x", "y")
    ]


def pick_path(pos, lo, hi, lane, edge=None):
    """Path for the next layer: inward from the nearest corner, or outward
    (a reversed inward spiral) if we're closer to the middle. Returns
    (waypoints, "inward"/"outward")."""
    best = None
    for pts in all_spirals(lo, hi, lane, edge):
        for path, kind in ((pts, "inward"), (pts[::-1], "outward")):
            d = abs(path[0][0] - pos[0]) + abs(path[0][1] - pos[1])
            if best is None or d < best[0]:
                best = (d, path, kind)
    return best[1], best[2]


def ring(lo, hi, inset, pos):
    """One lap around the layer, `inset` blocks from its edge, starting at the
    corner nearest to pos and coming back to it."""
    a, b = lo + inset, hi - inset
    corners = [(a, a), (b, a), (b, b), (a, b)]
    start = min(range(4), key=lambda i: abs(corners[i][0] - pos[0]) + abs(corners[i][1] - pos[1]))
    lap = corners[start:] + corners[:start]
    return lap + [lap[0]]

"""Hex grid geometry (axial coordinates, pointy-top), shared by hex-map games.

Cells are (q, r) tuples or "q,r" string keys (JSON-safe dict keys). The 6 directions go
east, north-east, north-west, west, south-west, south-east (DIRS[i] -> DIRS[i + 1] turns
60 degrees counter-clockwise on screen, y pointing down).

    from gamekit.hexes import DIRS, key, parse, distance, dist, neighbors, adjacent, disk, ring, rotate, rotations

    key(2, -1) -> "2,-1"            parse("2,-1") -> (2, -1)
    distance((0, 0), (2, -1)) -> 2  dist("0,0", "2,-1") -> 2 (same on keys)
    neighbors("0,0")                the 6 neighbouring keys (may be off the map)
    adjacent("0,0", "1,0") -> True
    disk(radius, center=(0, 0))     keys of every cell within `radius` of center (a hexagonal map)
    ring(radius, center=(0, 0))     keys of the cells exactly `radius` away, in order around the ring
    rotate((q, r), turns=1)         an offset turned 60 degrees `turns` times (about the origin)
    rotations(offsets)              the 6 rotations of a multi-cell shape (list of (q, r) offsets,
                                    the first is the anchor and stays at (0, 0)); index = turns
"""

DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]


def key(q, r):
    return f"{q},{r}"


def parse(k):
    q, r = k.split(",")
    return int(q), int(r)


def distance(a, b):
    dq, dr = a[0] - b[0], a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def dist(ka, kb):
    return distance(parse(ka), parse(kb))


def neighbors(k):
    q, r = parse(k)
    return [key(q + dq, r + dr) for dq, dr in DIRS]


def adjacent(a, b):
    return distance(parse(a), parse(b)) == 1


def disk(radius, center=(0, 0)):
    cq, cr = center
    return [key(cq + q, cr + r) for q in range(-radius, radius + 1)
            for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1)]


def ring(radius, center=(0, 0)):
    if radius == 0:
        return [key(*center)]
    q, r = center[0] + DIRS[4][0] * radius, center[1] + DIRS[4][1] * radius
    out = []
    for dq, dr in DIRS:
        for _ in range(radius):
            out.append(key(q, r))
            q, r = q + dq, r + dr
    return out


def rotate(offset, turns=1):
    q, r = offset
    for _ in range(turns % 6):
        q, r = -r, q + r
    return q, r


def rotations(offsets):
    return [[rotate(tuple(o), t) for o in offsets] for t in range(6)]

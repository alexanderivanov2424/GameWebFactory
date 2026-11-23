"""Metro Lanes map: the tile grid, its terrain and the buildable area that grows each week.

Tiles are indexed t = y * w + x. Terrain per tile: "." land, "~" water (roads need a bridge),
"^" mountain (roads need a tunnel). Terrain comes from a seed: one river crossing the map and a
few mountain blobs, kept off the starting area. The area (x0, y0, x1, y1, inclusive) starts
small around the centre and grows by AREA_STEP tiles on each side every week (like Mini
Motorways' zooming out); buildings spawn and roads go only inside it.
"""

import math

SIZES = {"small": (28, 18), "medium": (36, 22), "large": (44, 28)}
START_AREA = (14, 9)          # width, height of the first week's area
AREA_STEP = (1, 1)            # tiles added on each side (x, y) per week
LAND, WATER, MOUNTAIN = ".", "~", "^"

DIRS8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
DIRS4 = {"E": (1, 0), "W": (-1, 0), "S": (0, 1), "N": (0, -1)}


class Grid:
    def __init__(self, size, rng):
        self.w, self.h = SIZES[size]
        self.terrain = [LAND] * (self.w * self.h)
        aw, ah = START_AREA
        self.x0, self.y0 = (self.w - aw) // 2, (self.h - ah) // 2
        self.x1, self.y1 = self.x0 + aw - 1, self.y0 + ah - 1
        self._river(rng)
        self._mountains(rng)

    # --- geometry ---------------------------------------------------------------------

    def idx(self, x, y):
        return y * self.w + x

    def xy(self, t):
        return t % self.w, t // self.w

    def valid(self, t):
        return type(t) is int and 0 <= t < self.w * self.h

    def on_map(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def in_area(self, t):
        x, y = self.xy(t)
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def adjacent(self, a, b):
        """Neighbours in 8 directions (diagonals included)."""
        (ax, ay), (bx, by) = self.xy(a), self.xy(b)
        return a != b and abs(ax - bx) <= 1 and abs(ay - by) <= 1

    def dist(self, a, b):
        (ax, ay), (bx, by) = self.xy(a), self.xy(b)
        return math.hypot(ax - bx, ay - by)

    def step(self, t, dx, dy):
        """The tile next to t in direction (dx, dy), or None off the map."""
        x, y = self.xy(t)
        return self.idx(x + dx, y + dy) if self.on_map(x + dx, y + dy) else None

    def grow(self):
        sx, sy = AREA_STEP
        self.x0, self.y0 = max(0, self.x0 - sx), max(0, self.y0 - sy)
        self.x1, self.y1 = min(self.w - 1, self.x1 + sx), min(self.h - 1, self.y1 + sy)

    def area(self):
        return [self.x0, self.y0, self.x1, self.y1]

    def rows(self):
        return ["".join(self.terrain[y * self.w:(y + 1) * self.w]) for y in range(self.h)]

    # --- terrain generation -----------------------------------------------------------

    def _near_centre(self, x, y, margin):
        cx, cy = self.w // 2, self.h // 2
        return abs(x - cx) <= margin + 2 and abs(y - cy) <= margin

    def _river(self, rng):
        """A 1-2 tile wide river across the map (top to bottom or left to right), wandering."""
        vertical = rng.random() < 0.6
        across, along = (self.w, self.h) if vertical else (self.h, self.w)
        pos = rng.randint(across * 3 // 10, across * 6 // 10)
        if abs(pos - across // 2) < 3:
            pos += 4 if rng.random() < 0.5 else -4  # keep the very centre dry
        for k in range(along):
            width = 2 if rng.random() < 0.35 else 1
            for d in range(width):
                p = pos + d
                if 0 <= p < across:
                    self.terrain[self.idx(p, k) if vertical else self.idx(k, p)] = WATER
            if rng.random() < 0.3:
                new = max(1, min(across - 3, pos + rng.choice((-1, 1))))
                if new != pos:  # mark both columns of the bend so the water stays 4-connected
                    p = min(pos, new)
                    self.terrain[self.idx(p, k) if vertical else self.idx(k, p)] = WATER
                    self.terrain[self.idx(p + 1, k) if vertical else self.idx(k, p + 1)] = WATER
                pos = new

    def _mountains(self, rng):
        for _ in range(rng.randint(2, 4)):
            for _attempt in range(20):
                cx, cy = rng.randrange(self.w), rng.randrange(self.h)
                if not self._near_centre(cx, cy, 4):
                    break
            r = rng.choice((1.0, 1.5, 2.0))
            for y in range(int(cy - r), int(cy + r) + 1):
                for x in range(int(cx - r), int(cx + r) + 1):
                    if (self.on_map(x, y) and math.hypot(x - cx, y - cy) <= r
                            and not self._near_centre(x, y, 3) and self.terrain[self.idx(x, y)] == LAND):
                        self.terrain[self.idx(x, y)] = MOUNTAIN

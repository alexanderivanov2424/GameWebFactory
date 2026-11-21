"""The snowed-in valley: a W x H grid of lots, each holding some snow.

Lot index i = y * w + x. The cabin is in the middle; lots near it start cleared.
- depth[i]: the lot's starting snow (deeper further from the cabin, x1.3 in forests).
- snow[i]: snow left (float). reached[i]: 1 once the lot has been cleared at least once
  (it stays reached even if a blizzard drops snow back on it).
- feat[i]: feature char (FEATURES); hidden ones look plain until reached.
- dusted: reached lots a blizzard put snow back on (they don't count as cleared until dug again).
- targets: lots that can be worked: snow > 0 and reached or next to a reached lot.
- clear_lot() is the one place a lot is finished; it reports what was found there.

Rows sent to clients (rows()): {"snow": {"<y>": str}, "feat": {"<y>": str}}, one char per lot.
snow char: SNOW_CHARS[level], level 0 = no snow, else 1 + floor(log(snow) / log(LEVEL_BASE))
(clamped 1-61; the client shows about LEVEL_BASE ** (level - 1)).
feat char: lowercase = not reached yet, uppercase = reached (see FEATURES; "." and "," plain).
"""

import math

SNOW_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
LEVEL_BASE = 1.2
BASE_DEPTH = 8          # snow on a lot next to the cabin
DEPTH_SCALE = 6         # depth = BASE_DEPTH * (1 + distance / DEPTH_SCALE) ** 2
START_RADIUS = 2.5      # lots this close to the cabin start cleared
FOREST_SNOW = 1.3
# feature: (unreached char, reached char, chance per lot or None for forests, visible before reached)
FEATURES = {
    "plain": (".", ","), "cabin": ("x", "X"), "forest": ("t", "T"), "house": ("h", "H"),
    "gas": ("g", "G"), "cache": (".", "C"), "skier": (".", "K"),
}
SCATTER = {"house": 0.006, "gas": 0.0012, "cache": 0.01, "skier": 0.002}
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class World:
    def __init__(self, size, rng):
        self.w = self.h = size
        self.cx = self.cy = size // 2
        n = size * size
        self.kind = ["plain"] * n
        self._forests(rng)
        self.depth = [0.0] * n
        for i in range(n):
            x, y = i % size, i // size
            d = math.hypot(x - self.cx, y - self.cy)
            depth = BASE_DEPTH * (1 + d / DEPTH_SCALE) ** 2 * rng.uniform(0.8, 1.2)
            if self.kind[i] == "forest":
                depth *= FOREST_SNOW
            elif d > START_RADIUS + 3:
                roll = rng.random()
                for kind, chance in SCATTER.items():
                    if roll < chance:
                        self.kind[i] = kind
                        break
                    roll -= chance
            if d <= 1.5:
                self.kind[i] = "cabin"
            self.depth[i] = round(depth, 1)
        self.snow = list(self.depth)
        self.reached = bytearray(n)
        self.reached_list = []
        self.dusted = set()
        self.targets = set()
        self.dirty = set(range(size))
        self._rows = {"snow": {}, "feat": {}}
        for i in range(n):
            x, y = i % size, i // size
            if math.hypot(x - self.cx, y - self.cy) <= START_RADIUS:
                self.snow[i] = 0.0
                self._reach(i)

    def _forests(self, rng):
        size = self.w
        for _ in range(size * size // 400):
            fx, fy = rng.randrange(size), rng.randrange(size)
            radius = rng.uniform(1.5, 6)
            r = int(radius) + 1
            for y in range(max(0, fy - r), min(size, fy + r + 1)):
                for x in range(max(0, fx - r), min(size, fx + r + 1)):
                    if math.hypot(x - fx, y - fy) <= radius and rng.random() < 0.8:
                        self.kind[y * size + x] = "forest"

    # --- geometry --------------------------------------------------------------------

    def index(self, x, y):
        return y * self.w + x if 0 <= x < self.w and 0 <= y < self.h else None

    def xy(self, i):
        return i % self.w, i // self.w

    def neighbours(self, i):
        x, y = i % self.w, i // self.w
        for dx, dy in NEIGHBOURS:
            j = self.index(x + dx, y + dy)
            if j is not None:
                yield j

    def cleared(self):
        """Lots clear of snow right now (reached and not dusted)."""
        return len(self.reached_list) - len(self.dusted)

    def workable(self, i):
        return i in self.targets

    # --- changes ---------------------------------------------------------------------

    def _reach(self, i):
        self.reached[i] = 1
        self.reached_list.append(i)
        self.targets.discard(i)
        self.dirty.add(i // self.w)
        for j in self.neighbours(i):
            if not self.reached[j] and self.snow[j] > 0:
                self.targets.add(j)

    def dig(self, i, amount):
        """Remove up to `amount` snow from a workable lot. Returns (removed, found) where
        found is the feature kind if this cleared the lot for the first time (else None)."""
        if i not in self.targets or amount <= 0:
            return 0.0, None
        snow = self.snow[i]
        if amount < snow - 1e-6:
            before = self.level(snow)
            self.snow[i] = snow - amount
            if self.level(self.snow[i]) != before:
                self.dirty.add(i // self.w)
            return amount, None
        self.snow[i] = 0.0
        self.targets.discard(i)
        self.dirty.add(i // self.w)
        if self.reached[i]:
            self.dusted.discard(i)
            return snow, None
        self._reach(i)
        return snow, self.kind[i]

    def dust(self, i, fraction):
        """A blizzard drops snow back on reached lot i (not the cabin)."""
        if not self.reached[i] or self.kind[i] == "cabin":
            return
        self.snow[i] = min(self.depth[i], self.snow[i] + self.depth[i] * fraction)
        self.dusted.add(i)
        self.targets.add(i)
        self.dirty.add(i // self.w)

    def nearest_target(self, x, y, skip=(), limit=None):
        """The workable lot nearest to (x, y), not in skip; None if there is none.
        With limit, only looks at lots within that many lots (fast local search)."""
        if limit is not None:
            best, best_d = None, None
            r = int(limit) + 1
            ix, iy = round(x), round(y)
            for yy in range(max(0, iy - r), min(self.h, iy + r + 1)):
                row = yy * self.w
                for xx in range(max(0, ix - r), min(self.w, ix + r + 1)):
                    i = row + xx
                    if i in self.targets and i not in skip:
                        d = (xx - x) ** 2 + (yy - y) ** 2
                        if d <= limit * limit and (best_d is None or d < best_d):
                            best, best_d = i, d
            return best
        best, best_d, w = None, None, self.w
        for i in self.targets:
            if i in skip:
                continue
            d = (i % w - x) ** 2 + (i // w - y) ** 2
            if best_d is None or d < best_d:
                best, best_d = i, d
        return best

    # --- client rows -----------------------------------------------------------------

    @staticmethod
    def level(snow):
        if snow <= 0:
            return 0
        if snow < 1:
            return 1
        return max(1, min(61, 1 + int(math.log(snow) / math.log(LEVEL_BASE))))

    def rows(self):
        """Row strings for the client, rebuilt for dirty rows only."""
        if self.dirty:
            snow_rows, feat_rows = dict(self._rows["snow"]), dict(self._rows["feat"])
            w = self.w
            for y in self.dirty:
                lo = y * w
                snow_rows[str(y)] = "".join(SNOW_CHARS[self.level(self.snow[i])] for i in range(lo, lo + w))
                feat_rows[str(y)] = "".join(FEATURES[self.kind[i]][1 if self.reached[i] else 0]
                                            for i in range(lo, lo + w))
            self._rows = {"snow": snow_rows, "feat": feat_rows}
            self.dirty = set()
        return self._rows

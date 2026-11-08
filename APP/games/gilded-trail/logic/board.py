"""Gilded Trail: the hex map. Geometry helpers and the procedural board generator.

Hexes use axial coordinates (pointy-top), keyed "q,r". A map is a chain of radius-3 hex
tiles (37 spaces each). A map preset (maps/*.json) gives:
    dirs      the offset from each tile to the next, an index into TILE_OFFSETS (0 = east,
              1 = south-east, 2 = south, ... 5 = north-east); a map has len(dirs) + 1 tiles; consecutive tiles share a border;
              turns must stay gentle or non-neighbouring tiles touch (rejected)
    weights   how often each terrain is picked: machete (jungle), paddle (water), coin
              (village), mountain (impassable)
    hazards   multiplier for rubble and base camp spaces per tile
    seed      fixed seed, so a preset is the same board every game
The "random" map uses a random chain of `tiles` tiles and a seed from the host (or a fresh one).

Board(...) builds, for one seed:
    hexes      {key: {"q", "r", "tile", "t", "v", "goal"?}}
               t: machete | paddle | coin | rubble | camp | mountain | start; v = requirement
    starts     4 start spaces on the far edge of tile 0 (one explorer each)
    goals      3 golden city spaces just outside the last tile (entering one = arriving)
    blockades  one per tile border: {"id", "t": machete|paddle|coin|rubble, "v", "edges"}
               edges = [[a, b], ...] neighbouring hex pairs across that border
The generator retries until every start reaches the goals and every border has at least 3
passable crossings (explorers can't fully jam a chokepoint).
"""

import random

DIRS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
TILE_OFFSETS = [(7, -3), (3, 4), (-4, 7), (-7, 3), (-3, -4), (4, -7)]
RANDOM_WEIGHTS = {"machete": 5, "paddle": 2.2, "coin": 2, "mountain": 1.5}
FIRST_TILE_WEIGHTS = {"machete": 5, "paddle": 2, "coin": 2, "mountain": 0.6}
BLOCKADE_WEIGHTS = {"machete": 3, "paddle": 2, "coin": 2, "rubble": 2}
START_SPACES = 4
GOAL_SPACES = 3
MIN_CROSSINGS = 3


def key(q, r):
    return f"{q},{r}"


def parse(k):
    q, r = k.split(",")
    return int(q), int(r)


def distance(a, b):
    dq, dr = a[0] - b[0], a[1] - b[1]
    return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


def neighbors(k):
    q, r = parse(k)
    return [key(q + dq, r + dr) for dq, dr in DIRS]


def adjacent(a, b):
    return distance(parse(a), parse(b)) == 1


def pick_weighted(rng, weights):
    total = sum(weights.values())
    x = rng.random() * total
    for name, weight in weights.items():
        x -= weight
        if x <= 0:
            return name
    return next(iter(weights))


def random_dirs(rng, tiles):
    dirs = [rng.choice((0, 1))]
    while len(dirs) < tiles - 1:
        prev = dirs[-1]
        dirs.append(rng.choice([d for d in (prev, (prev + 1) % 6, (prev + 5) % 6) if d in (0, 1, 5)]))
    return dirs


def passable(h):
    return h is not None and h["t"] not in ("mountain", "start")


class Board:
    def __init__(self, preset=None, seed=1, tiles=6):
        """preset: a MAPS entry (its own seed is used), or None for a random map of `tiles` tiles."""
        rng = random.Random(preset["seed"] if preset else seed)
        if preset:
            self.name, dirs, weights, hazards = preset["name"], preset["dirs"], preset["weights"], preset["hazards"]
        else:
            self.name, dirs, weights, hazards = "Random expedition", random_dirs(rng, tiles), RANDOM_WEIGHTS, 1
        for _ in range(500):
            if self._generate(rng, dirs, weights, hazards) and self._connected():
                return
        raise ValueError("Could not generate a playable board.")

    # --- Generation ------------------------------------------------------------------------

    def _generate(self, rng, dirs, weights, hazards):
        centers = [(0, 0)]
        for d in dirs:
            o = TILE_OFFSETS[d]
            centers.append((centers[-1][0] + o[0], centers[-1][1] + o[1]))
        count = len(centers)
        for i in range(count):
            for j in range(i + 2, count):
                if distance(centers[i], centers[j]) <= 7:
                    raise ValueError("Map layout lets non-neighbouring tiles touch.")
        hexes = {}
        for ti, c in enumerate(centers):
            depth = ti / (count - 1)
            w = FIRST_TILE_WEIGHTS if ti == 0 else {**weights, "mountain": weights["mountain"] + depth * 0.8}
            seeds = []
            for _ in range(7):
                while True:
                    q, r = c[0] + rng.randint(-3, 3), c[1] + rng.randint(-3, 3)
                    if distance((q, r), c) <= 3:
                        break
                seeds.append(((q, r), pick_weighted(rng, w)))
            for dq in range(-3, 4):
                for dr in range(-3, 4):
                    q, r = c[0] + dq, c[1] + dr
                    if distance((q, r), c) > 3:
                        continue
                    t = min(seeds, key=lambda s: distance((q, r), s[0]) + rng.random() * 0.9)[1]
                    v = 0
                    if t != "mountain":
                        x = rng.random()
                        if ti == 0 or x < 0.55 - 0.2 * depth:
                            v = 1
                        elif x < 0.88 - 0.08 * depth:
                            v = 2
                        else:
                            v = 4 if t == "coin" and rng.random() < 0.3 else 3
                    hexes[key(q, r)] = {"q": q, "r": r, "tile": ti, "t": t, "v": v}
            if ti > 0:
                cells = [h for h in hexes.values() if h["tile"] == ti and h["t"] != "mountain"]
                rubble = round(rng.randint(0, 2) * hazards)
                camps = max(1, round(rng.randint(1, 2) * hazards))
                for j in range(rubble + camps):
                    h = rng.choice(cells)
                    h["t"] = "rubble" if j < rubble else "camp"
                    h["v"] = rng.randint(1, 3 if ti >= count / 2 else 2)
        # Start spaces: contiguous ring cells on the side of tile 0 away from tile 1.
        ring = [h for h in hexes.values() if h["tile"] == 0 and distance((h["q"], h["r"]), centers[0]) == 3]
        far = max(ring, key=lambda h: distance((h["q"], h["r"]), centers[1]))
        ring.sort(key=lambda h: distance((h["q"], h["r"]), (far["q"], far["r"])))
        self.starts = []
        for h in ring[:START_SPACES]:
            h["t"], h["v"] = "start", 0
            self.starts.append(key(h["q"], h["r"]))
        # Golden city: contiguous cells just outside the last tile, away from the previous one.
        last = count - 1
        outside = sorted({n for k, h in hexes.items() if h["tile"] == last for n in neighbors(k) if n not in hexes})
        out = [parse(k) for k in outside]
        far_goal = max(out, key=lambda p: distance(p, centers[last - 1]))
        out.sort(key=lambda p: distance(p, far_goal))
        self.goals = []
        for i, (q, r) in enumerate(out[:GOAL_SPACES]):
            k = key(q, r)
            hexes[k] = {"q": q, "r": r, "tile": last, "t": "paddle" if i == 1 else "machete", "v": 1, "goal": True}
            self.goals.append(k)
        self.hexes = hexes
        self.tiles = count
        self.blockades = []
        for ti in range(count - 1):
            t = pick_weighted(rng, BLOCKADE_WEIGHTS)
            v = 2 if rng.random() < (0.6 if ti >= count / 2 else 0.3) else 1
            edges = [[k, n] for k, h in sorted(hexes.items()) if h["tile"] == ti
                     for n in neighbors(k) if n in hexes and hexes[n]["tile"] == ti + 1]
            self.blockades.append({"id": ti, "t": t, "v": v, "edges": edges})
        return True

    def _connected(self):
        seen, stack = set(self.goals), list(self.goals)
        while stack:
            for n in neighbors(stack.pop()):
                h = self.hexes.get(n)
                if h is None or n in seen:
                    continue
                if h["t"] == "start":
                    seen.add(n)
                elif passable(h):
                    seen.add(n)
                    stack.append(n)
        if not all(k in seen for k in self.starts):
            return False
        crossings = [0] * self.tiles
        for k, h in self.hexes.items():
            if passable(h):
                for n in neighbors(k):
                    g = self.hexes.get(n)
                    if passable(g) and g["tile"] == h["tile"] + 1:
                        crossings[h["tile"]] += 1
        return all(c >= MIN_CROSSINGS for c in crossings[:-1])

    # --- Queries ---------------------------------------------------------------------------

    def border(self, a, b):
        """The blockade between two neighbouring hexes on different tiles, or None."""
        ta, tb = self.hexes[a]["tile"], self.hexes[b]["tile"]
        if ta == tb:
            return None
        return self.blockades[min(ta, tb)]

    def public(self):
        return {
            "name": self.name,
            "hexes": self.hexes,
            "starts": self.starts,
            "goals": self.goals,
            "tiles": self.tiles,
        }

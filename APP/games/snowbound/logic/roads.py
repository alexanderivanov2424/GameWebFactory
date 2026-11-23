"""Roads: levels, laying them, and the route fields machines follow over the road network.

Levels (LEVELS[n], n = world.road[i]): 1 Track, 2 Gravel, 3 Paved, 4 Heated. Machines move
`unit` x faster on a road lot without snow, people `walk` x faster (avatars.py; client/grid.js
mirrors it), and Heated roads never get snowed over in blizzards (survival.dust). Drift Dogs,
Road Graders and Jet Blower beams leave Track; players lay roads at any level on reached lots
(not the cabin) and upgrade them, paying the difference between the level costs (lay()).

Route fields (Field): for every road lot connected to a source through road lots, the travel cost
to the nearest source (in lots at a machine's off-road speed: an edge costs the mean of
1 / unit-speed of its two lots) and the next lot toward it. Network keeps two:
    drop:   sources = the cabin's lots, Snow Depots and Old Rail Stations (snow drop points)
    market: sources = the cabin's lots and Old Rail Stations (where goods sell)
Roads only ever get added or faster and sources only get added, so costs only go down: changes
are relaxed incrementally (a lazy Dijkstra kept in a heap) with at most BUDGET lots settled per
field per tick (Network.update, called every tick). Following next pointers always lowers the
cost, so a route can't loop. hauling.py uses the fields to plan trips (straight off-road,
then along the road network).
"""

import heapq
import math
from array import array

from gamekit import LobbyError

# (name, unit speed x, walk speed x, $ to reach this level from nothing)
LEVELS = [
    {"name": "No road", "unit": 1.0, "walk": 1.0, "cost": 0},
    {"name": "Track", "unit": 1.6, "walk": 1.2, "cost": 25},
    {"name": "Gravel", "unit": 2.3, "walk": 1.35, "cost": 300},
    {"name": "Paved", "unit": 3.2, "walk": 1.5, "cost": 4000},
    {"name": "Heated", "unit": 4.2, "walk": 1.7, "cost": 50000},
]
TOP = len(LEVELS) - 1
HEATED = 4
MAX_LOTS = 200      # lots per lay() call
BUDGET = 2000       # lots settled per field per tick
INF = float("inf")


def unit_speed(world, i):
    """Speed multiplier for a machine on lot i (roads without snow are faster)."""
    level = world.road[i]
    return LEVELS[level]["unit"] if level and world.snow[i] <= 0 else 1.0


def lay(match, pid, lots, level):
    """pid lays road of `level` on each [x, y] in lots (skipping lots already that good).
    Pays as it goes; refuses with a message if nothing could be laid. Returns lots changed."""
    p = match.player(pid)
    world = match.world
    if level not in range(1, TOP + 1):
        raise LobbyError("Unknown road level.")
    done, broke, bad = 0, False, False
    for x, y in lots[:MAX_LOTS]:
        i = world.index(x, y)
        if i is None or not world.reached[i] or world.kind[i] == "cabin":
            bad = True
            continue
        if world.road[i] >= level:
            continue
        cost = LEVELS[level]["cost"] - LEVELS[world.road[i]]["cost"]
        if cost > p.cash + 1e-9:
            broke = True
            break
        p.cash -= cost
        world.make_road(i, level)
        done += 1
    if not done and broke:
        raise LobbyError(f"Not enough cash for {LEVELS[level]['name']} road.")
    if not done and bad:
        raise LobbyError("Roads go on cleared ground (not the cabin).")
    return done


class Field:
    """Travel cost from road lots to the nearest source, kept up to date incrementally."""

    def __init__(self, world):
        self.world = world
        n = world.w * world.h
        self.cost = array("d", [INF]) * n
        self.next = array("l", [-1]) * n
        self.src = array("l", [-1]) * n
        self.sources = []
        self.heap = []

    def _speed(self, i):
        level = self.world.road[i]
        return LEVELS[level]["unit"] if level else 1.0

    def _edge(self, i, j):
        return 0.5 * (1 / self._speed(i) + 1 / self._speed(j))

    def _node(self, i):
        return self.world.road[i] > 0 or self.src[i] == i

    def add_source(self, i):
        if self.src[i] == i:
            return
        self.sources.append(i)
        self.cost[i], self.next[i], self.src[i] = 0.0, -1, i
        heapq.heappush(self.heap, (0.0, i))

    def touch(self, i):
        """Lot i became road or got faster: take the best route through a neighbour, then spread."""
        cost = self.cost
        best, via = cost[i], -1
        for j in self.world.neighbours(i):
            if cost[j] < INF:
                c = cost[j] + self._edge(j, i)
                if c < best - 1e-9:
                    best, via = c, j
        if via >= 0:
            cost[i], self.next[i], self.src[i] = best, via, self.src[via]
        if cost[i] < INF:
            heapq.heappush(self.heap, (cost[i], i))

    def run(self, budget=BUDGET):
        cost, heap, world = self.cost, self.heap, self.world
        while heap and budget > 0:
            c, i = heapq.heappop(heap)
            if c > cost[i] + 1e-9:
                continue
            budget -= 1
            for j in world.neighbours(i):
                if not self._node(j):
                    continue
                nc = c + self._edge(i, j)
                if nc < cost[j] - 1e-9:
                    cost[j], self.next[j], self.src[j] = nc, i, self.src[i]
                    heapq.heappush(heap, (nc, j))

    def chain(self, i, limit=20000):
        """Lots from i along next pointers to its source (both included)."""
        out = [i]
        while self.next[i] >= 0 and len(out) < limit:
            i = self.next[i]
            out.append(i)
        return out


class Network:
    """The two route fields (drop points, markets) and their upkeep."""

    def __init__(self, world):
        self.world = world
        self.drop = Field(world)
        self.market = Field(world)
        for i in range(world.w * world.h):
            if world.kind[i] == "cabin":
                self.drop.add_source(i)
                self.market.add_source(i)

    def add_drop(self, i, market=False):
        self.drop.add_source(i)
        if market:
            self.market.add_source(i)

    def update(self):
        world = self.world
        if world.road_changed:
            for i in world.road_changed:
                self.drop.touch(i)
                self.market.touch(i)
            world.road_changed = []
        self.drop.run()
        self.market.run()


def nearest_road(field, x, y, radius):
    """(lot, distance) pairs of routed road lots within radius of lot coordinates (x, y)."""
    world = field.world
    r = int(radius) + 1
    ix, iy = round(x), round(y)
    out = []
    for yy in range(max(0, iy - r), min(world.h, iy + r + 1)):
        row = yy * world.w
        for xx in range(max(0, ix - r), min(world.w, ix + r + 1)):
            i = row + xx
            if field.cost[i] < INF:
                d = math.hypot(xx - x, yy - y)
                if d <= radius:
                    out.append((i, d))
    return out

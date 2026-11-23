"""Metro Lanes road network: who built which tile, how tiles link, and routes through it.

Pieces (each owned by the player who built it):
- Road tiles on land. A road tile costs 1 road from your stock. Tiles link to neighbours in 8
  directions when you draw between them (linking two existing tiles is free). Two diagonal
  links may not cross.
- Bridges / tunnels: drawing from land straight (not diagonally) into water / a mountain builds a
  whole span across it (at most MAX_SPAN tiles) and the road where it lands. Costs 1 bridge /
  tunnel (plus 1 road for each new land tile). Span tiles link only along the span.
- Roundabouts and traffic lights: placed on a road tile (anyone's), they make that junction
  carry more traffic (traffic.py).
Erasing: your own road tile (refunds 1 road; its links and features on it
go, refunded to whoever owned them), a whole bridge/tunnel of yours (refunds it), or a
roundabout/light you placed (erased first if the tile has one of yours).

Buildings (city.py) occupy tiles (`blocked`) and hang off the network by a fixed driveway: a
building's node tile links to its door tile while that door tile has a road. The graph's nodes
are road tiles plus building nodes; edges() lists them. `version` goes up on every change;
route trees (shortest paths towards one node, by driving time) are cached per version.
"""

import heapq

from gamekit import LobbyError

ROAD, BRIDGE, TUNNEL = "r", "b", "t"
MAX_SPAN = {BRIDGE: 4, TUNNEL: 5}
ROAD_SPEED = 2.0          # tiles per second
JUNCTION_COST = 0.4       # extra seconds a route counts for a junction without a roundabout
FEATURES = {"roundabout": "roundabouts", "light": "lights"}   # feature -> stock item


class Road:
    __slots__ = ("owner", "kind", "feature", "feat_owner", "span")

    def __init__(self, owner, kind=ROAD, span=None):
        self.owner = owner
        self.kind = kind
        self.feature = None      # "roundabout" | "light"
        self.feat_owner = None
        self.span = span         # bridge/tunnel id


class RoadNet:
    def __init__(self, grid, players):
        self.grid = grid
        self.players = players     # pid -> Player (for costs and refunds)
        self.roads = {}            # tile -> Road
        self.links = {}            # tile -> set of linked neighbour tiles
        self.spans = {}            # id -> {"tiles": [...], "owner", "kind"}
        self.blocked = set()       # tiles covered by buildings
        self.doors = {}            # building node tile -> its door tile
        self.attached = {}         # door tile -> set of building node tiles
        self.version = 0
        self._next = 1
        self._trees = {}
        self._trees_version = -1

    # --- graph ------------------------------------------------------------------------

    def edges(self, n):
        """Tiles a car can drive to from n."""
        for m in self.links.get(n, ()):
            yield m
        if n in self.roads:
            yield from self.attached.get(n, ())
        door = self.doors.get(n)
        if door is not None and door in self.roads:
            yield door

    def has_edge(self, u, v):
        return any(m == v for m in self.edges(u))

    def degree(self, n):
        return sum(1 for _ in self.edges(n))

    def junction(self, n):
        """A road tile where three or more ways meet (cars take turns there)."""
        return n in self.roads and self.degree(n) >= 3

    def length(self, u, v):
        return self.grid.dist(u, v)

    def speed(self, u, v):
        return ROAD_SPEED

    def tree(self, target):
        """{node: (seconds to target, next node towards target)} for every node that can reach it."""
        if self._trees_version != self.version:
            self._trees, self._trees_version = {}, self.version
        if target in self._trees:
            return self._trees[target]
        best = {target: (0.0, None)}
        heap = [(0.0, target)]
        while heap:
            d, n = heapq.heappop(heap)
            if d > best[n][0]:
                continue
            for m in self.edges(n):
                cost = d + self.length(n, m) / self.speed(n, m)
                road = self.roads.get(m)
                if road is not None and road.feature != "roundabout" and self.junction(m):
                    cost += JUNCTION_COST
                if m not in best or cost < best[m][0]:
                    best[m] = (cost, n)
                    heapq.heappush(heap, (cost, m))
        self._trees[target] = best
        return best

    def route(self, start, target):
        """List of nodes from start to target (both included), or None if unreachable."""
        tree = self.tree(target)
        if start not in tree:
            return None
        path = [start]
        while path[-1] != target:
            path.append(tree[path[-1]][1])
        return path

    # --- buildings --------------------------------------------------------------------

    def add_building(self, tiles, node, door):
        self.blocked.update(tiles)
        self.doors[node] = door
        self.attached.setdefault(door, set()).add(node)
        self.version += 1

    def free_land(self, t):
        """Land a building could stand on: no road, no building."""
        return self.grid.terrain[t] == "." and t not in self.roads and t not in self.blocked

    # --- building roads ---------------------------------------------------------------

    def _check_tile(self, t):
        g = self.grid
        if not g.in_area(t):
            raise LobbyError("That's outside the city limits.")
        if t in self.blocked:
            raise LobbyError("There's a building there.")
        if g.terrain[t] != ".":
            raise LobbyError("Roads need a bridge or tunnel there.")

    def draw(self, pid, a, b):
        """Draw a road from tile a to the neighbouring tile b."""
        g = self.grid
        if not (g.valid(a) and g.valid(b) and g.adjacent(a, b)):
            raise LobbyError("Draw between neighbouring tiles.")
        player = self.players[pid]
        # A building's driveway: just put a road on its door tile.
        for node, other in ((a, b), (b, a)):
            if node in self.doors:
                if self.doors[node] != other:
                    raise LobbyError("Connect buildings at their driveway.")
                if other not in self.roads:
                    self._check_tile(other)
                    player.spend("roads")
                    self._add(other, Road(pid))
                return
        if g.terrain[b] != "." and b not in self.roads:
            return self._span(pid, a, b)
        for t in (a, b):
            road = self.roads.get(t)
            if road is not None and road.kind != ROAD:
                raise LobbyError("Bridges and tunnels only connect at their ends.")
        new = [t for t in (a, b) if t not in self.roads]
        for t in new:
            self._check_tile(t)
        (ax, ay), (bx, by) = g.xy(a), g.xy(b)
        if ax != bx and ay != by:  # diagonal: may not cross the other diagonal
            c, d = g.idx(bx, ay), g.idx(ax, by)
            if d in self.links.get(c, ()):
                raise LobbyError("Roads can't cross there. Make a junction instead.")
        if not new and b in self.links.get(a, ()):
            return
        player.spend("roads", len(new))
        for t in new:
            self._add(t, Road(pid))
        self._link(a, b)

    def _span(self, pid, a, b):
        """A bridge or tunnel from land tile a across the water/mountain starting at b."""
        g = self.grid
        kind = BRIDGE if g.terrain[b] == "~" else TUNNEL
        name = "bridge" if kind == BRIDGE else "tunnel"
        (ax, ay), (bx, by) = g.xy(a), g.xy(b)
        dx, dy = bx - ax, by - ay
        if dx and dy:
            raise LobbyError(f"A {name} must go straight across, not diagonally.")
        if g.terrain[a] != "." or a in self.blocked:
            raise LobbyError(f"Start the {name} from land.")
        if a in self.roads and self.roads[a].kind != ROAD:
            raise LobbyError(f"Start the {name} from land.")
        tiles, t = [], b
        while t is not None and g.terrain[t] == g.terrain[b]:
            if t in self.roads:
                raise LobbyError(f"There's already a {name} there.")
            tiles.append(t)
            if len(tiles) > MAX_SPAN[kind]:
                raise LobbyError(f"Too far: a {name} spans at most {MAX_SPAN[kind]} tiles.")
            t = g.step(t, dx, dy)
        if t is None or g.terrain[t] != ".":
            raise LobbyError(f"The {name} has nowhere to land.")
        for s in tiles:
            if not g.in_area(s):
                raise LobbyError("That's outside the city limits.")
        new = [s for s in (a, t) if s not in self.roads]
        for s in new:
            self._check_tile(s)
        if t in self.roads and self.roads[t].kind != ROAD:
            raise LobbyError(f"The {name} has nowhere to land.")
        player = self.players[pid]
        item = "bridges" if kind == BRIDGE else "tunnels"
        if player.stock[item] < 1:
            raise LobbyError(f"You need a {name} to cross there.")
        player.spend("roads", len(new))
        player.spend(item, 1, name + "s")
        sid = self._id()
        self.spans[sid] = {"tiles": tiles, "owner": pid, "kind": kind}
        for s in new:
            self._add(s, Road(pid))
        for s in tiles:
            self._add(s, Road(pid, kind, sid))
        chain = [a, *tiles, t]
        for u, v in zip(chain, chain[1:]):
            self._link(u, v)

    def place(self, pid, t, feature):
        road = self.roads.get(t) if self.grid.valid(t) else None
        if road is None or road.kind != ROAD:
            raise LobbyError("Place it on a road.")
        if road.feature:
            raise LobbyError("That road already has one.")
        self.players[pid].spend(FEATURES[feature], 1, feature + "s")
        road.feature, road.feat_owner = feature, pid
        self.version += 1

    def erase(self, pid, t):
        road = self.roads.get(t) if self.grid.valid(t) else None
        if road is None:
            raise LobbyError("There's no road there.")
        if road.feature and road.feat_owner == pid:
            self._drop_feature(road)
            self.version += 1
            return
        if road.owner != pid:
            raise LobbyError("That's not your road.")
        if road.span is not None:
            span = self.spans.pop(road.span)
            for s in span["tiles"]:
                self._remove(s)
            self.players[pid].refund("bridges" if span["kind"] == BRIDGE else "tunnels")
            return
        self._remove(t)
        self.players[pid].refund("roads")

    # --- internals --------------------------------------------------------------------

    def _id(self):
        self._next += 1
        return str(self._next - 1)

    def _add(self, t, road):
        self.roads[t] = road
        self.links.setdefault(t, set())
        self.version += 1

    def _link(self, a, b):
        self.links.setdefault(a, set()).add(b)
        self.links.setdefault(b, set()).add(a)
        self.version += 1

    def _drop_feature(self, road):
        self.players[road.feat_owner].refund(FEATURES[road.feature])
        road.feature = road.feat_owner = None

    def _remove(self, t):
        road = self.roads.pop(t)
        if road.feature:
            self._drop_feature(road)
        for m in self.links.pop(t, ()):
            self.links[m].discard(t)
        self.version += 1

    def step_owner(self, u, v):
        """Who gets the points for a car driving u -> v: (pid, points) or None. The road tile v
        earns its builder 1 point."""
        road = self.roads.get(v)
        return (road.owner, 1) if road is not None else None

    def owner_shares(self, path):
        """Who built the road a car drove along `path`: {pid: points} (see step_owner)."""
        shares = {}
        for u, v in zip(path, path[1:]):
            got = self.step_owner(u, v)
            if got is not None:
                shares[got[0]] = shares.get(got[0], 0) + got[1]
        return shares

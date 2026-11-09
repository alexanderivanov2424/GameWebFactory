"""Bastion: the shared board, a map's terrain plus everything placed on it, and the geometry rules.

Cells are (x, y). Each cell holds at most one of: a building tile, a road, a wall or a blight
(an enemy's tile). Only grass can be built on; buildings (not roads or walls) may also go over
road tiles, which they replace, unless goods are waiting on them. "Next to" always means
orthogonally adjacent.

    board = Board(game_map)          places the map's starting town (owner None)
    board.structures                 {uid: Structure} buildings (roads and walls are cell sets:
                                     board.roads, board.walls); board.at {(x, y): uid}
    board.blights                    {(x, y): {"name", "icon", "foe": enemy index, "lair": bool}}
    board.cargo                      {(x, y) road cell: {good: n}} goods a haul left on the road
    board.add_cargo(cell, good) / board.take_cargo(cell, good)   one good on / off a road tile
    board.version                    bumped on every change (Match caches placement targets by it)
    board.footprint(kind, rotation, x, y)   the cells a placement covers (x, y = top-left)
    board.check(kind, rotation, x, y)       those cells, or LobbyError why it can't go there
    board.place(kind, rotation, x, y, owner) -> Structure (None for a road or wall)
    board.near(cells, what)          how many of `what` are next to `cells`: terrain cells, "empty"
                                     grass cells, road/wall cells, or distinct buildings of a kind
    board.link(structure)            "depot" (next to a working depot), "road" (a road next to it
                                     reaches a cell next to a depot) or None (cut off)
    board.road_distances()           {road cell: steps from it into a depot} for roads that reach one
    board.toward_depot(cell, dist)   the next road cell on the shortest way to a depot
    board.protected(cell)            next to a wall, or within a watchtower's reach
    board.raid_targets(prefer)       unprotected, unruined tiles of buildings (not the keep)
    board.ruin(cell) / board.repair(structure)   damage one tile / fix every ruined tile
    board.free_spots(cells, rng)     random top-left spots where a blight shape fits on empty grass
    board.public()                   tiles, blights and cargo for clients (terrain is in the catalog)
"""

from dataclasses import dataclass, field

from gamekit import LobbyError

from .structures import BUILDABLE, STRUCTURES, TERRAIN, a, describe

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass
class Structure:
    uid: int
    kind: str
    cells: list
    owner: str = None  # who built it (None: the starting town)
    ruined: set = field(default_factory=set)
    plague: int = None  # index of the enemy that spread it
    frozen: int = 0  # the round it can't work in
    worked: bool = False  # worked this round
    store: dict = field(default_factory=dict)  # goods waiting to be hauled

    @property
    def spec(self):
        return STRUCTURES[self.kind]

    def stored(self):
        return sum(self.store.values())


class Board:
    def __init__(self, game_map, log=None):
        self.width, self.height = game_map.width, game_map.height
        self.terrain = [[TERRAIN[ch] for ch in row] for row in game_map.rows]
        self.structures = {}
        self.at = {}
        self.roads = set()
        self.walls = set()
        self.blights = {}
        self.cargo = {}
        self.next_uid = 1
        self.version = 0
        for entry in game_map.start:
            try:
                self.check(entry["structure"], entry["rotation"], entry["x"], entry["y"], start=True)
                self.place(entry["structure"], entry["rotation"], entry["x"], entry["y"], None)
            except LobbyError as error:
                if log:
                    log.error("Map %s: start %s doesn't fit: %s", game_map.name, entry, error)

    # --- geometry ------------------------------------------------------------------------------

    def inside(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def taken(self, cell):
        return cell in self.at or cell in self.roads or cell in self.walls or cell in self.blights

    def empty(self, cell):
        return self.inside(*cell) and self.terrain[cell[1]][cell[0]] == BUILDABLE and not self.taken(cell)

    def footprint(self, kind, rotation, x, y):
        return [(x + dx, y + dy) for dy, dx in STRUCTURES[kind]["pieces"][rotation % 4]]

    def neighbors(self, cells):
        own = set(cells)
        return {(x + dx, y + dy) for x, y in cells for dx, dy in DIRS
                if (x + dx, y + dy) not in own and self.inside(x + dx, y + dy)}

    def near(self, cells, what):
        around = self.neighbors(cells)
        if what == "empty":
            return sum(1 for c in around if self.empty(c))
        if what == "road":
            return len(around & self.roads)
        if what == "wall":
            return len(around & self.walls)
        if what in STRUCTURES:
            return len({self.at[c] for c in around if c in self.at and self.structures[self.at[c]].kind == what})
        return sum(1 for x, y in around if self.terrain[y][x] == what)

    def blighted(self, cells):
        return sum(1 for c in self.neighbors(cells) if c in self.blights)

    # --- placing -----------------------------------------------------------------------------

    def check(self, kind, rotation, x, y, start=False):
        spec = STRUCTURES[kind]
        if spec["price"] is None and not start:
            raise LobbyError(f"{a(spec['name']).capitalize()} can't be built.")
        cells = self.footprint(kind, rotation, x, y)
        for cell in cells:
            if not self.inside(*cell):
                raise LobbyError("That doesn't fit on the board.")
            if cell in self.roads and not spec["tile"]:
                if cell in self.cargo:
                    raise LobbyError("Goods are waiting on that road: haul them away first.")
                continue
            if not self.empty(cell):
                raise LobbyError("Build only on empty grass or over roads." if not spec["tile"] else "Build only on empty grass.")
        for cond in spec["requires"]:
            if self.near(cells, cond["near"]) < cond["min"]:
                raise LobbyError(f"{a(spec['name']).capitalize()} must be {describe(cond, STRUCTURES)}.")
        return cells

    def place(self, kind, rotation, x, y, owner):
        cells = self.footprint(kind, rotation, x, y)
        self.version += 1
        tile = STRUCTURES[kind]["tile"]
        if tile:
            (self.roads if tile == "road" else self.walls).update(cells)
            return None
        self.roads.difference_update(cells)  # a building replaces the roads under it
        structure = Structure(self.next_uid, kind, cells, owner)
        self.next_uid += 1
        self.structures[structure.uid] = structure
        for cell in cells:
            self.at[cell] = structure.uid
        return structure

    def remove(self, uid):
        structure = self.structures.pop(uid)
        for cell in structure.cells:
            del self.at[cell]
        self.version += 1
        return structure

    def free_spots(self, cells, rng):
        spots = [(x, y) for y in range(self.height) for x in range(self.width)
                 if all(self.empty((x + dx, y + dy)) for dy, dx in cells)]
        rng.shuffle(spots)
        return spots

    def add_blight(self, cell, name, icon, foe, lair=False):
        self.blights[cell] = {"name": name, "icon": icon, "foe": foe, "lair": lair}
        self.version += 1

    def remove_blight(self, cell):
        del self.blights[cell]
        self.version += 1

    def add_cargo(self, cell, good):
        pile = self.cargo.setdefault(cell, {})
        pile[good] = pile.get(good, 0) + 1
        self.version += 1

    def take_cargo(self, cell, good):
        pile = self.cargo[cell]
        pile[good] -= 1
        if not pile[good]:
            del pile[good]
        if not pile:
            del self.cargo[cell]
        self.version += 1

    # --- links and protection ----------------------------------------------------------------

    def depot_cells(self):
        return {c for s in self.structures.values() if s.spec["depot"] and not s.ruined for c in s.cells}

    def road_distances(self):
        """{road cell: steps from it into a depot} (a road next to a depot: 1) for every road
        whose network touches a depot."""
        depots = self.depot_cells()
        frontier = sorted(c for c in self.roads if self.neighbors([c]) & depots)
        dist = {c: 1 for c in frontier}
        while frontier:
            following = []
            for x, y in frontier:
                for dx, dy in DIRS:
                    cell = (x + dx, y + dy)
                    if cell in self.roads and cell not in dist:
                        dist[cell] = dist[(x, y)] + 1
                        following.append(cell)
            frontier = following
        return dist

    def road_reach(self):
        """Road cells whose road network touches a depot."""
        return set(self.road_distances())

    def toward_depot(self, cell, dist):
        x, y = cell
        closer = sorted(c for c in ((x + dx, y + dy) for dx, dy in DIRS) if dist.get(c) == dist[cell] - 1)
        return closer[0] if closer else cell

    def link(self, structure, reach=None):
        around = self.neighbors(structure.cells)
        if structure.spec["depot"] or around & self.depot_cells():
            return "depot"
        if around & (self.road_reach() if reach is None else reach):
            return "road"
        return None

    def protected(self, cell):
        x, y = cell
        if self.neighbors([cell]) & self.walls:
            return True
        for s in self.structures.values():
            reach = s.spec["protects"]
            if reach and not s.ruined and any(abs(x - sx) <= reach and abs(y - sy) <= reach for sx, sy in s.cells):
                return True
        return False

    def raid_targets(self, prefer=()):
        """Cells a raid may ruin: preferred kinds first if any are open."""
        open_cells = [c for s in self.structures.values() if s.kind != "keep"
                      for c in s.cells if c not in s.ruined and not self.protected(c)]
        preferred = [c for c in open_cells if self.structures[self.at[c]].kind in prefer]
        return sorted(preferred or open_cells)

    def ruin(self, cell):
        """Ruin a building tile or break a wall/road tile. Returns the destroyed Structure if
        that was its last whole tile, else None."""
        self.version += 1
        if cell in self.walls:
            self.walls.discard(cell)
            return None
        if cell in self.roads:
            self.roads.discard(cell)
            self.cargo.pop(cell, None)
            return None
        structure = self.structures[self.at[cell]]
        structure.ruined.add(cell)
        if len(structure.ruined) == len(structure.cells):
            return self.remove(structure.uid)
        return None

    def repair(self, structure):
        structure.ruined.clear()
        self.version += 1

    # --- clients -----------------------------------------------------------------------------

    def public(self):
        return {
            "roads": sorted(f"{x},{y}" for x, y in self.roads),
            "walls": sorted(f"{x},{y}" for x, y in self.walls),
            "blights": {f"{x},{y}": dict(b) for (x, y), b in self.blights.items()},
            "cargo": {f"{x},{y}": {"goods": dict(pile), "safe": self.protected((x, y))}
                      for (x, y), pile in self.cargo.items()},
        }

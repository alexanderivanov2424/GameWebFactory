"""Bastion: the shared map, its terrain plus everything placed on it, and the geometry rules.

Cells are (x, y). Each cell holds at most one of: a building, a road tile, (dormant enemy code
only) a wall tile or a blight. Every structure is one tile and belongs to the player who placed
it; road tiles are owned too. "Next to" means orthogonally adjacent; "within n" (reach) means a
square of radius n (diagonals count).

    board = Board(game_map)
    board.structures                 {uid: Structure}; board.at {(x, y): uid}
    board.roads                      {(x, y): owner pid}
    board.version                    bumped on every change (views cache targets by it)
    board.check(kind, x, y, owner=None)   the cells, or LobbyError why it can't go there (empty
                                     grass, the structure's "requires"; reach is checked by callers)
    board.place(kind, x, y, owner, tokens=0) -> Structure (planned: tokens > 0)
    board.add_road(cell, owner)
    board.terrain_at(cell) / board.empty(cell) / board.near(cells, what)
    board.owned(pid) / board.anchors(pid)   pid's structures / the cells their reach counts from
                                     (built buildings and roads; plans don't extend reach)
    board.reach(pid, n)              every cell within n of an anchor (cached by version)
    board.public()                   structures and roads for clients (terrain is in the catalog)
Dormant enemy support (attacks.py, combat.py, foes.py; not called while enemies are off): walls,
blights, protected / raid_targets / loot_targets / ruin / repair / free_spots / add_blight.
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
    owner: str = ""
    tokens: int = 0  # build tokens left; 0 = built
    ruined: set = field(default_factory=set)  # dormant enemy code
    plague: int = None
    frozen: int = 0
    level: int = 0
    store: dict = field(default_factory=dict)

    @property
    def spec(self):
        return STRUCTURES[self.kind]

    @property
    def built(self):
        return self.tokens == 0

    @property
    def cell(self):
        return self.cells[0]

    def stored(self):
        return sum(self.store.values())


class Board:
    def __init__(self, game_map):
        self.width, self.height = game_map.width, game_map.height
        self.terrain = [[TERRAIN[ch] for ch in row] for row in game_map.rows]
        self.structures = {}
        self.at = {}
        self.roads = {}
        self.walls = set()
        self.blights = {}
        self.next_uid = 1
        self.version = 0
        self._reach = {}

    # --- geometry ------------------------------------------------------------------------------

    def inside(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def terrain_at(self, cell):
        return self.terrain[cell[1]][cell[0]]

    def taken(self, cell):
        return cell in self.at or cell in self.roads or cell in self.walls or cell in self.blights

    def empty(self, cell):
        return self.inside(*cell) and self.terrain_at(cell) == BUILDABLE and not self.taken(cell)

    def neighbors(self, cells):
        own = set(cells)
        return {(x + dx, y + dy) for x, y in cells for dx, dy in DIRS
                if (x + dx, y + dy) not in own and self.inside(x + dx, y + dy)}

    def near(self, cells, what):
        around = self.neighbors(cells)
        if what == "empty":
            return sum(1 for c in around if self.empty(c))
        if what == "road":
            return len(around & set(self.roads))
        if what == "wall":
            return len(around & self.walls)
        if what in STRUCTURES:
            return len({self.at[c] for c in around if c in self.at and self.structures[self.at[c]].kind == what})
        return sum(1 for c in around if self.terrain_at(c) == what)

    # --- ownership and reach -------------------------------------------------------------------

    def owned(self, pid):
        return [s for _, s in sorted(self.structures.items()) if s.owner == pid]

    def anchors(self, pid):
        return [s.cell for s in self.owned(pid) if s.built] + [c for c, o in self.roads.items() if o == pid]

    def reach(self, pid, n):
        key = (pid, n)
        cached = self._reach.get(key)
        if cached and cached[0] == self.version:
            return cached[1]
        cells = set()
        for ax, ay in self.anchors(pid):
            for y in range(max(0, ay - n), min(self.height, ay + n + 1)):
                for x in range(max(0, ax - n), min(self.width, ax + n + 1)):
                    cells.add((x, y))
        self._reach[key] = (self.version, cells)
        return cells

    # --- placing -----------------------------------------------------------------------------

    def check(self, kind, x, y):
        spec = STRUCTURES[kind]
        cell = (x, y)
        if not self.inside(x, y):
            raise LobbyError("That's off the board.")
        if not self.empty(cell):
            raise LobbyError("Build only on empty grass.")
        for cond in spec["requires"]:
            if self.near([cell], cond["near"]) < cond["min"]:
                raise LobbyError(f"{a(spec['name']).capitalize()} must be {describe(cond, STRUCTURES)}.")
        return [cell]

    def place(self, kind, x, y, owner, tokens=0):
        self.version += 1
        structure = Structure(self.next_uid, kind, [(x, y)], owner, tokens)
        self.next_uid += 1
        self.structures[structure.uid] = structure
        self.at[(x, y)] = structure.uid
        return structure

    def add_road(self, cell, owner):
        self.roads[cell] = owner
        self.version += 1

    def remove(self, uid):
        structure = self.structures.pop(uid)
        for cell in structure.cells:
            del self.at[cell]
        self.version += 1
        return structure

    # --- dormant enemy support (attacks.py, combat.py, foes.py) -------------------------------

    def footprint(self, kind, rotation, x, y):
        return [(x + dx, y + dy) for dy, dx in STRUCTURES[kind]["pieces"][rotation % 4]]

    def free_spots(self, cells, rng):
        spots = [(x, y) for y in range(self.height) for x in range(self.width)
                 if all(self.empty((x + dx, y + dy)) for dy, dx in cells)]
        rng.shuffle(spots)
        return spots

    def add_blight(self, cell, name, icon, foe, lair=False):
        self.blights[cell] = {"name": name, "icon": icon, "foe": foe, "lair": lair, "strikes": 0}
        self.version += 1

    def remove_blight(self, cell):
        del self.blights[cell]
        self.version += 1

    def protected(self, cell):
        return bool(self.neighbors([cell]) & self.walls)

    def raid_targets(self, prefer=()):
        open_cells = [c for s in self.structures.values() if s.kind != "keep"
                      for c in s.cells if c not in s.ruined and not self.protected(c)]
        preferred = [c for c in open_cells if self.structures[self.at[c]].kind in prefer]
        return sorted(preferred or open_cells)

    def loot_targets(self):
        return [s for _, s in sorted(self.structures.items())
                if s.stored() and not all(self.protected(c) for c in s.cells)]

    def ruin(self, cell):
        self.version += 1
        if cell in self.walls:
            self.walls.discard(cell)
            return None
        if cell in self.roads:
            del self.roads[cell]
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
            "structures": {str(uid): {"kind": s.kind, "x": s.cell[0], "y": s.cell[1], "owner": s.owner,
                                      "tokens": s.tokens}
                           for uid, s in self.structures.items()},
            "roads": {f"{x},{y}": owner for (x, y), owner in self.roads.items()},
        }

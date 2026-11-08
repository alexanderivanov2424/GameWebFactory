"""Bastion: loading the map files (content/maps/*.json): terrain, the keep and the two roads.

A map file:
    {"name": "Green Valley",
     "terrain": ["................", ...],    one string per row, all the same length:
                                              "." grass (buildable), "^" rocks, "~" water, "T" forest
     "keep": [x, y],
     "roads": {"main": [[x, y], ...], "flank": [[x, y], ...]}}
Roads are waypoints joined by straight horizontal/vertical runs; each must end on the keep.
The first cell of a road is where enemies enter (nothing may be built there). Roads may merge.

    MAPS     {id: Map}   (Map: name, width, height, terrain rows, keep (x, y),
                          roads {name: [(x, y), ...] every cell in order}, road_cells set,
                          entrances set, remaining {cell: fewest steps to the keep}, public())
    DEFAULT  the map picked by default ("valley" if it exists)
"""

import logging

from gamekit.data import load_json_dir, text

from .cards import CONTENT
from .enemies import ROADS

log = logging.getLogger("bastion")

TERRAIN = {".": "grass", "^": "rocks", "~": "water", "T": "forest"}
MAX_SIZE = 24


class Map:
    def __init__(self, map_id, name, terrain, keep, roads):
        self.id = map_id
        self.name = name
        self.terrain = terrain
        self.height = len(terrain)
        self.width = len(terrain[0])
        self.keep = keep
        self.roads = roads
        self.road_cells = {cell for cells in roads.values() for cell in cells}
        self.entrances = {cells[0] for cells in roads.values()}
        self.remaining = {}
        for cells in roads.values():
            for i, cell in enumerate(cells):
                left = len(cells) - 1 - i
                self.remaining[cell] = min(left, self.remaining.get(cell, left))

    def inside(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def ground(self, x, y):
        return self.terrain[y][x]

    def public(self):
        return {"name": self.name, "width": self.width, "height": self.height, "terrain": self.terrain,
                "keep": list(self.keep), "roads": {name: [list(c) for c in cells] for name, cells in self.roads.items()}}


def _point(value, width, height):
    if (not isinstance(value, list) or len(value) != 2 or not all(type(v) is int for v in value)
            or not (0 <= value[0] < width and 0 <= value[1] < height)):
        raise ValueError(f"{value!r} isn't a cell on the map")
    return tuple(value)


def expand(points):
    """Waypoints -> every cell along straight runs between them."""
    cells = [points[0]]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if x1 != x2 and y1 != y2:
            raise ValueError(f"road runs from {[x1, y1]} to {[x2, y2]} must be straight")
        dx, dy = (x2 > x1) - (x2 < x1), (y2 > y1) - (y2 < y1)
        x, y = x1, y1
        while (x, y) != (x2, y2):
            x, y = x + dx, y + dy
            cells.append((x, y))
    if len(set(cells)) != len(cells):
        raise ValueError("a road crosses itself")
    return cells


def parse_map(map_id, data):
    terrain = data.get("terrain")
    if (not isinstance(terrain, list) or not 4 <= len(terrain) <= MAX_SIZE
            or not all(isinstance(r, str) and 4 <= len(r) <= MAX_SIZE for r in terrain)
            or len({len(r) for r in terrain}) != 1):
        raise ValueError(f"terrain must be 4-{MAX_SIZE} rows of the same length (4-{MAX_SIZE})")
    if any(ch not in TERRAIN for row in terrain for ch in row):
        raise ValueError(f"terrain may only use {''.join(TERRAIN)}")
    width, height = len(terrain[0]), len(terrain)
    keep = _point(data.get("keep"), width, height)
    roads_data = data.get("roads")
    if not isinstance(roads_data, dict) or set(roads_data) != set(ROADS):
        raise ValueError(f"roads must have exactly {', '.join(ROADS)}")
    roads = {}
    for name in ROADS:
        points = roads_data[name]
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError(f"road {name} needs at least 2 waypoints")
        cells = expand([_point(p, width, height) for p in points])
        if cells[-1] != keep:
            raise ValueError(f"road {name} must end on the keep")
        roads[name] = cells
    return Map(map_id, text(data, "name", 40, required=True), list(terrain), keep, roads)


MAPS = load_json_dir(CONTENT / "maps", parse_map, log)
DEFAULT = "valley" if "valley" in MAPS else next(iter(MAPS), None)

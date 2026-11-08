"""Bastion: loading the map files (content/maps/*.json): terrain and the starting town.

    MAPS     {id: GameMap}; DEFAULT is the map id the host's Map setting starts on
    GameMap  name, width, height, rows (terrain letters, structures.TERRAIN),
             start: [{"structure": id, "x", "y", "rotation"}] (tiles take one entry per piece)
    MAX_SIZE largest width/height (server.py validates cells against it)
A map is only checked for shape here; Board places the start town when a game begins and
logs a start entry that doesn't fit (tests check the real maps place every entry).
"""

import logging
from dataclasses import dataclass

from gamekit.data import load_json_dir, text, whole

from .structures import CONTENT, STRUCTURES, TERRAIN

log = logging.getLogger("bastion")

MAX_SIZE = 24
DEFAULT = "valley"


@dataclass
class GameMap:
    name: str
    width: int
    height: int
    rows: list
    start: list


def parse_map(map_id, data):
    rows = data.get("rows")
    if not isinstance(rows, list) or not 6 <= len(rows) <= MAX_SIZE or not all(isinstance(r, str) for r in rows):
        raise ValueError(f"rows must be 6 to {MAX_SIZE} strings")
    width = len(rows[0])
    if not 6 <= width <= MAX_SIZE or any(len(r) != width for r in rows):
        raise ValueError(f"rows must all have the same length, 6 to {MAX_SIZE}")
    if any(ch not in TERRAIN for row in rows for ch in row):
        raise ValueError(f"rows may only use {sorted(TERRAIN)}")
    start = data.get("start", [])
    if not isinstance(start, list):
        raise ValueError("start must be a list")
    entries = []
    for item in start:
        if not isinstance(item, dict) or item.get("structure") not in STRUCTURES:
            raise ValueError("each start entry needs a known structure")
        entries.append({"structure": item["structure"], "x": whole(item, "x", 0, width - 1),
                        "y": whole(item, "y", 0, len(rows) - 1), "rotation": whole(item, "rotation", 0, 3, default=0)})
    if not any(e["structure"] == "keep" for e in entries):
        raise ValueError("start needs a keep")
    return GameMap(text(data, "name", 30, required=True), width, len(rows), rows, entries)


MAPS = load_json_dir(CONTENT / "maps", parse_map, log)

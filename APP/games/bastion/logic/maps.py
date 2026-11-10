"""Bastion: loading the map files (content/maps/*.json): terrain only (players place their own
keep, house and farm in the setup phase: setup.py).

    MAPS     {id: GameMap}; DEFAULT is the map id the host's Map setting starts on
    GameMap  name, width, height, rows (terrain letters, structures.TERRAIN)
    MAX_SIZE largest width/height (server.py validates cells against it)
"""

import logging
from dataclasses import dataclass

from gamekit.data import load_json_dir, text

from .structures import CONTENT, TERRAIN

log = logging.getLogger("bastion")

MAX_SIZE = 40
DEFAULT = "valley"


@dataclass
class GameMap:
    name: str
    width: int
    height: int
    rows: list


def parse_map(map_id, data):
    rows = data.get("rows")
    if not isinstance(rows, list) or not 6 <= len(rows) <= MAX_SIZE or not all(isinstance(r, str) for r in rows):
        raise ValueError(f"rows must be 6 to {MAX_SIZE} strings")
    width = len(rows[0])
    if not 6 <= width <= MAX_SIZE or any(len(r) != width for r in rows):
        raise ValueError(f"rows must all have the same length, 6 to {MAX_SIZE}")
    if any(ch not in TERRAIN for row in rows for ch in row):
        raise ValueError(f"rows may only use {sorted(TERRAIN)}")
    return GameMap(text(data, "name", 30, required=True), width, len(rows), rows)


MAPS = load_json_dir(CONTENT / "maps", parse_map, log)

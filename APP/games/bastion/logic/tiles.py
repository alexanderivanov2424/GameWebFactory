"""Bastion: road and wall tiles, placed and removed one cell at a time (no cards).

The team keeps a stock of each tile kind (match.tile_stock, {"road": n, "wall": n}). On their
turn in the act phase, a player places one tile on empty grass from that stock; with the stock
at 0 it first buys BATCH tiles for the tile's "cost" from its structure file (road: 1 gold,
wall: 1 stone). Removing a road or wall tile is free and refunds nothing. Buildings may still go
over road tiles, replacing them (board.check).

    KINDS                            tile structure ids ("road", "wall")
    BATCH                            tiles one purchase adds to the stock
    place(match, pid, kind, x, y)    LobbyError if it can't go there or the team can't pay
    remove(match, pid, x, y)
    targets(match) -> {kind: ["x,y", ...], "remove": ["x,y", ...]}   every legal cell (public;
                                     cached by board.version)
"""

from gamekit import LobbyError

from .cards import amount_text
from .structures import STRUCTURES, TILES, a

KINDS = TILES
BATCH = 3  # tiles bought at once (tune)


def place(match, pid, kind, x, y):
    seat = match.acting(pid)
    spec = STRUCTURES.get(kind)
    if kind not in KINDS or spec is None:
        raise LobbyError("Pick a road or a wall.")
    match.board.check(kind, 0, x, y)
    bought = ""
    if match.tile_stock[kind] <= 0:
        match.pay(spec["cost"], f"{BATCH} {spec['name'].lower()} tiles")
        match.tile_stock[kind] += BATCH
        bought = f" (bought {BATCH} for {amount_text(spec['cost'])})"
    match.tile_stock[kind] -= 1
    match.board.place(kind, 0, x, y)
    match.write(f"{seat.name} laid {a(spec['name'].lower())} tile{bought}.", pid)


def remove(match, pid, x, y):
    seat = match.acting(pid)
    board, cell = match.board, (x, y)
    if cell not in board.roads and cell not in board.walls:
        raise LobbyError("There's no road or wall there.")
    name = "road" if cell in board.roads else "wall"
    board.clear(cell)
    match.write(f"{seat.name} removed {a(name)} tile.", pid)


def targets(match):
    board = match.board
    cached = match.__dict__.get("_tile_targets")
    if cached and cached[0] == board.version:
        return cached[1]
    found = {}
    for kind in KINDS:
        spots = []
        for y in range(board.height):
            for x in range(board.width):
                try:
                    board.check(kind, 0, x, y)
                except LobbyError:
                    continue
                spots.append(f"{x},{y}")
        found[kind] = spots
    found["remove"] = sorted(f"{x},{y}" for x, y in board.roads | board.walls)
    match._tile_targets = (board.version, found)
    return found

"""Bastion: road and wall tiles, bought and removed one cell at a time (no cards).

Any player who hasn't ended their turn may, at any time, pay a tile's "cost" from its structure
file (road: 1 gold, wall: 1 stone) to place one road or wall tile on empty grass, or pay REMOVE_COST to take one road
or wall tile away. A road tile with a carriage on it can't be removed (nor built over).
Buildings may still go over road tiles, replacing them (board.check).

    KINDS                            tile structure ids ("road", "wall")
    place(match, pid, kind, x, y)    LobbyError if it can't go there or the team can't pay
    remove(match, pid, x, y)
    targets(match) -> {kind: ["x,y", ...], "remove": ["x,y", ...]}   every legal cell (public;
                                     cached by board.version)
"""

from gamekit import LobbyError

from .structures import STRUCTURES, TILES, a

KINDS = TILES
REMOVE_COST = {"gold": 1}


def place(match, pid, kind, x, y):
    seat = match.acting(pid)
    spec = STRUCTURES.get(kind)
    if kind not in KINDS or spec is None:
        raise LobbyError("Pick a road or a wall.")
    match.board.check(kind, 0, x, y)
    match.pay(spec["cost"], a(spec["name"]).capitalize())
    match.board.place(kind, 0, x, y, pid)
    match.write(f"{seat.name} laid {a(spec['name'].lower())} tile.", pid)


def removable(board, cell):
    return (cell in board.roads or cell in board.walls) and not any(c.cell == cell for c in board.carriages.values())


def remove(match, pid, x, y):
    seat = match.acting(pid)
    board, cell = match.board, (x, y)
    if cell not in board.roads and cell not in board.walls:
        raise LobbyError("There's no road or wall there.")
    if not removable(board, cell):
        raise LobbyError("A carriage is on that road: wait until it has passed.")
    name = "road" if cell in board.roads else "wall"
    match.pay(REMOVE_COST, "Removing it")
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
    found["remove"] = sorted(f"{x},{y}" for x, y in board.roads | board.walls if removable(board, (x, y)))
    match._tile_targets = (board.version, found)
    return found

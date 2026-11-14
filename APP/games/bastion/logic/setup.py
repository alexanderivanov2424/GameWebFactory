"""Bastion: the setup phase, before round 1. Players take turns in seat order; on their turn a
player places their keep, then a house, then a farm (PIECES), one click each, built at once.

    PIECES               ("keep", "house", "farm")
    KEEP_GAP             a keep goes at least this far (square distance) from every other
                         player's structures, so cities start apart
    order(pids)          [(pid, kind)] the whole setup sequence
    current(match)       (pid, kind) placing now, or None when setup is over
    reason(match, pid, cell) -> None if pid may put their current piece there, else why not
    spots(match, pid)    [(x, y)] where pid's current piece may go (empty when it isn't their go)
    place(match, pid, x, y)   puts the piece down (built, its units added); after the last one
                         the first round starts (Match.start_round)
    drop(match, pid)     a leaving player's remaining pieces are skipped
The house and farm must be within units.REACH of the player's keep (their reach), like units.
"""

from gamekit import LobbyError

from . import units
from .structures import STRUCTURES, a

PIECES = ("keep", "house", "farm")
KEEP_GAP = 5


def order(pids):
    return [(pid, kind) for pid in pids for kind in PIECES]


def current(match):
    if match.phase != "setup" or match.setup_index >= len(match.setup_order):
        return None
    return match.setup_order[match.setup_index]


def reason(match, pid, cell):
    board = match.board
    now = current(match)
    if now is None or now[0] != pid:
        return "It's not your turn to place."
    kind = now[1]
    try:
        board.check(kind, *cell)
    except LobbyError as error:
        return str(error)
    if kind == "keep":
        x, y = cell
        for s in board.structures.values():
            sx, sy = s.cell
            if s.owner != pid and max(abs(sx - x), abs(sy - y)) < KEEP_GAP:
                return f"Keeps go at least {KEEP_GAP} tiles from other players' cities."
    elif cell not in board.reach(pid, units.REACH):
        return f"{a(STRUCTURES[kind]['name']).capitalize()} goes within {units.REACH} tiles of your keep."
    return None


def spots(match, pid):
    now = current(match)
    if now is None or now[0] != pid:
        return []
    board = match.board
    return [(x, y) for y in range(board.height) for x in range(board.width) if reason(match, pid, (x, y)) is None]


def place(match, pid, x, y):
    seat = match.seat(pid)
    if match.phase != "setup":
        raise LobbyError("Setup is over.")
    why = reason(match, pid, (x, y))
    if why:
        raise LobbyError(why)
    kind = match.setup_order[match.setup_index][1]
    structure = match.board.place(kind, x, y, pid)
    seat.units += structure.spec["units"]
    match.write(f"{seat.name} placed their {structure.spec['name']}.", pid)
    advance(match)


def advance(match):
    match.setup_index += 1
    while match.setup_index < len(match.setup_order) and match.setup_order[match.setup_index][0] not in match.seats:
        match.setup_index += 1
    match.step += 1
    if match.setup_index >= len(match.setup_order):
        match.start_round()


def drop(match, pid):
    now = current(match)
    match.setup_order = [(p, k) for i, (p, k) in enumerate(match.setup_order)
                         if p != pid or i < match.setup_index]
    if now and now[0] == pid and match.seats:
        match.setup_index -= 1
        advance(match)

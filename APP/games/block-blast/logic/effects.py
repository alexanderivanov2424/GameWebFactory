"""Block Blast: what happens when rows and columns clear: spoiling (by tile type) and symbol effects.

    resolve_clears(match, pid)   clears every full row and column on pid's board at once and
                                 applies the symbols on the cleared cells to pid

Spoiling: a cleared line holding a tile whose type `spoils` (goblin) has no effect. A symbol
still counts if another cleared line through its cell is unspoiled, or if its own tile is
`unspoilable` (grey). Each cell counts once either way.

Symbols: EFFECTS has one function per symbol name, called as effect(clear, n) with the number
counted. `clear` (a Clear) holds the seat, the log phrases (`gains`) and the attack total; the
attack itself is dealt after every effect ran (deal_attack). Effects run in symbols.SYMBOLS order.
"""

from . import board as boards
from .symbols import SYMBOLS
from .tiles import TILE_TYPES

SIEGE_PER_STRENGTH = 3  # siege symbols cleared for +1 strength (+1 damage to each attack)


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


class Clear:
    def __init__(self, seat):
        self.seat = seat
        self.gains = []  # log phrases, e.g. "+2 gold"
        self.attacks = 0
        self.strength = seat["strength"]  # from before this clear: new strength counts next time


def coin(clear, n):
    clear.seat["gold"] += n
    clear.gains.append(f"+{n} gold")


def attack(clear, n):
    clear.attacks += n


def shield(clear, n):
    clear.seat["shield"] += n
    clear.gains.append(f"+{n} shield")


def chapel(clear, n):
    clear.seat["chapels"] += n
    clear.gains.append(f"+{plural(n, 'card removal')}")


def siege(clear, n):
    seat = clear.seat
    gained, seat["siege"] = divmod(seat["siege"] + n, SIEGE_PER_STRENGTH)
    seat["strength"] += gained
    clear.gains.append(f"+{n} siege" + (f" → +{gained} strength" if gained else ""))


def decorative(clear, n):
    """Art only (the goblin face): the goblin tile under it is what spoils lines."""


EFFECTS = {"coin": coin, "attack": attack, "shield": shield, "chapel": chapel, "siege": siege, "goblin": decorative}


def deal_attack(match, clear):
    """An attack = a clear with attack symbols: 1 damage each, plus the attacker's strength once.
    The target's shield absorbs it first. Returns the target if it was hit."""
    target = clear.seat["target"]
    if not clear.attacks or target is None:
        return None
    damage = clear.attacks + clear.strength
    defender = match.seats[target]
    blocked = min(defender["shield"], damage)
    defender["shield"] -= blocked
    defender["health"] = max(0, defender["health"] - (damage - blocked))
    clear.gains.append(f"{damage} damage to {match.names[target]}" + (f" ({blocked} blocked by their shield)" if blocked else ""))
    return target


def resolve_clears(match, pid):
    seat = match.seats[pid]
    grid = seat["board"]
    rows, cols = boards.full_lines(grid)
    if not rows and not cols:
        return
    spoils = lambda cell: TILE_TYPES[cell[0]].spoils  # noqa: E731
    spoiled_rows = [r for r in rows if any(spoils(grid[r][c]) for c in range(boards.SIZE))]
    spoiled_cols = [c for c in cols if any(spoils(grid[r][c]) for r in range(boards.SIZE))]
    live = boards.line_cells([r for r in rows if r not in spoiled_rows], [c for c in cols if c not in spoiled_cols])
    removed = boards.clear(grid, rows, cols)
    counts = {}
    for r, c, (tile, symbol) in removed:
        if symbol and ((r, c) in live or TILE_TYPES[tile].unspoilable):
            counts[symbol] = counts.get(symbol, 0) + 1
    clear = Clear(seat)
    for name in SYMBOLS:
        if counts.get(name):
            EFFECTS[name](clear, counts[name])
    target = deal_attack(match, clear)
    lines = [plural(len(rows), "row")] * bool(rows) + [plural(len(cols), "column")] * bool(cols)
    text = f"{match.names[pid]} cleared {' and '.join(lines)}" + (f": {', '.join(clear.gains)}." if clear.gains else ".")
    spoiled = len(spoiled_rows) + len(spoiled_cols)
    if spoiled:
        text += f" Goblins spoiled {plural(spoiled, 'line')}."
    match.add_log(pid, text)
    match.last_clear = {"step": match.step, "pid": pid, "cells": [[r, c] for r, c, _ in removed]}
    if target is not None and match.seats[target]["health"] == 0:
        match.knock_out(target, f"{match.names[target]} is knocked out!")

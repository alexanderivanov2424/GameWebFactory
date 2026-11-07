"""Block Blast: what a clear does: which lines clear, spoiling (by tile type) and symbol effects.

Pure rules on one board and seat; Match (match.py) runs them after each placement and writes
the log, the clear animation and knock-outs.

    cleared = clear_lines(board)     empties every full row and column at once; returns a Cleared
                                     (rows, cols, removed cells, symbol counts, spoiled lines),
                                     or None if no line is full
    clear = apply_symbols(seat, cleared.counts)
                                     runs EFFECTS on the seat (gold, shield, chapels, siege) and
                                     returns a Clear: log phrases (`gains`) and the attack's damage
    blocked = deal_damage(defender, damage)
                                     the defender's shield absorbs first, the rest is health lost

Spoiling: a cleared line holding a tile whose type `spoils` (goblin) has no effect. A symbol
still counts if another cleared line through its cell is unspoiled, or if its own tile is
`unspoilable` (grey). Each cell counts once either way.

Symbols: EFFECTS has one function per symbol name, called as effect(clear, n) with the number
counted; they run in symbols.SYMBOLS order. HELP has one line per symbol name saying what it does,
for the client's legend (keep it true when an effect changes). An attack (a clear with attack symbols) does 1
damage per symbol plus the attacker's strength once, using the strength from before the clear.
"""

from dataclasses import dataclass

from . import board as boards
from .symbols import SYMBOLS
from .tiles import TILE_TYPES

SIEGE_PER_STRENGTH = 3  # siege symbols cleared for +1 strength (+1 damage to each attack)


def plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


@dataclass
class Cleared:
    rows: list  # indexes of the cleared rows
    cols: list
    removed: list  # [(r, c, (tile, symbol))], each cell once
    counts: dict  # {symbol name: n} that take effect (not spoiled)
    spoiled: int  # lines with no effect


def clear_lines(grid):
    rows, cols = boards.full_lines(grid)
    if not rows and not cols:
        return None
    spoils = lambda cell: TILE_TYPES[cell[0]].spoils  # noqa: E731
    spoiled_rows = [r for r in rows if any(spoils(grid[r][c]) for c in range(boards.SIZE))]
    spoiled_cols = [c for c in cols if any(spoils(grid[r][c]) for r in range(boards.SIZE))]
    live = boards.line_cells([r for r in rows if r not in spoiled_rows], [c for c in cols if c not in spoiled_cols])
    removed = boards.clear(grid, rows, cols)
    counts = {}
    for r, c, (tile, symbol) in removed:
        if symbol and ((r, c) in live or TILE_TYPES[tile].unspoilable):
            counts[symbol] = counts.get(symbol, 0) + 1
    return Cleared(rows, cols, removed, counts, len(spoiled_rows) + len(spoiled_cols))


class Clear:
    """What the symbols of one clear did for the seat that cleared."""

    def __init__(self, seat):
        self.seat = seat
        self.gains = []  # log phrases, e.g. "+2 gold"
        self.attacks = 0
        self.strength = seat.strength  # from before this clear: new strength counts next time

    @property
    def damage(self):
        return self.attacks + self.strength if self.attacks else 0


def coin(clear, n):
    clear.seat.gold += n
    clear.gains.append(f"+{n} gold")


def attack(clear, n):
    clear.attacks += n


def shield(clear, n):
    clear.seat.shield += n
    clear.gains.append(f"+{n} shield")


def chapel(clear, n):
    clear.seat.chapels += n
    clear.gains.append(f"+{plural(n, 'card removal')}")


def siege(clear, n):
    seat = clear.seat
    gained, seat.siege = divmod(seat.siege + n, SIEGE_PER_STRENGTH)
    seat.strength += gained
    clear.gains.append(f"+{n} siege" + (f" → +{gained} strength" if gained else ""))


def decorative(clear, n):
    """Art only (the goblin face): the goblin tile under it is what spoils lines. Symbols with
    this effect are also left out of card symbol counts (cards.symbol_counts)."""


EFFECTS = {"coin": coin, "attack": attack, "shield": shield, "chapel": chapel, "siege": siege, "goblin": decorative}

HELP = {
    "coin": "+1 gold.",
    "attack": "1 damage to the player you're aiming at. Your strength adds to the total once per clear.",
    "shield": "+1 shield: absorbs 1 incoming damage, then it's used up. Shield drops by 1 at the start of your turn.",
    "chapel": "+1 card removal: spend it any time to delete a card from your deck for good.",
    "siege": f"Every {SIEGE_PER_STRENGTH} cleared give +1 strength (+1 damage to each of your attacks).",
    "goblin": "Just the face on goblin tiles: the tile is what spoils lines.",
}


def apply_symbols(seat, counts):
    clear = Clear(seat)
    for name in SYMBOLS:
        if counts.get(name):
            EFFECTS[name](clear, counts[name])
    return clear


def deal_damage(defender, damage):
    blocked = min(defender.shield, damage)
    defender.shield -= blocked
    defender.health = max(0, defender.health - (damage - blocked))
    return blocked

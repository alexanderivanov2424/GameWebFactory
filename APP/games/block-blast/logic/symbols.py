"""Block Blast: symbols. A symbol sits on a tile (tiles.py) and does something when its cell is
cleared; what each one does is in effects.py (EFFECTS, one function per symbol name).

    SYMBOLS        {name: Symbol}   in display/log order (effects run in this order)
    BY_CODE        {code: Symbol}   one uppercase letter, used in card files' "symbols" rows and
                                    in the client state
    public_table() {code: name} for the game state

A symbol that is only art (the goblin face: the goblin *tile* is what spoils lines, see
tiles.py) has the no-op effects.decorative as its effect; that also leaves it out of card
symbol counts (cards.py).

Adding a symbol: a Symbol here, its effect function and HELP line in effects.py, and an icon + `.sym-<name>`
style in the client (SYMBOL_ICONS in client/draw.js, index.html). Any tile type can carry it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Symbol:
    name: str
    code: str  # one uppercase letter


SYMBOLS = {s.name: s for s in (
    Symbol("coin", "C"),
    Symbol("attack", "A"),
    Symbol("shield", "S"),
    Symbol("chapel", "R"),
    Symbol("siege", "E"),
    Symbol("goblin", "G"),  # drawn on goblin tiles; art only (effects.decorative)
)}
BY_CODE = {s.code: s for s in SYMBOLS.values()}


def public_table():
    return {s.code: s.name for s in SYMBOLS.values()}

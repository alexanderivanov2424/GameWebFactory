"""Block Blast: tile types. A tile fills one board cell; a symbol (symbols.py) may sit on it.

Tiles and symbols are separate: a card places tiles of some type, and any of them may carry a
symbol. A tile type's behaviour is a set of flags read by the rules (effects.py):

    spoils        a cleared row or column holding this tile has no effect (goblin)
    unspoilable   the symbol on this tile counts even in a spoiled line (grey)

    TILE_TYPES     {name: TileType}   in display order
    BY_CODE        {code: TileType}   one-letter codes used in card files and the client state
    DEFAULT_TILE   "blue"
    public_table() {code: {"name", "spoils", "unspoilable", "help"}} for the game state (help:
                   the line players read in the client's legend)

Adding a tile type: one TileType here (pick an unused lowercase code, write its help), a
`.tile-<name>` style in client/index.html, and any new behaviour flag read in effects.py.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TileType:
    name: str
    code: str  # one lowercase letter (card files' "tiles" rows, client state)
    help: str  # one line for the client's legend
    spoils: bool = False
    unspoilable: bool = False


TILE_TYPES = {t.name: t for t in (
    TileType("blue", "b", "A plain tile: its symbol counts when its row or column clears."),
    TileType("grey", "g", "Goblins can't spoil it: its symbol counts even when a goblin tile spoils the line.",
             unspoilable=True),
    TileType("goblin", "x", "Spoils lines: a cleared row or column with a goblin tile in it has no effect "
             "(symbols on grey tiles still count).", spoils=True),
)}
BY_CODE = {t.code: t for t in TILE_TYPES.values()}
DEFAULT_TILE = "blue"


def public_table():
    return {t.code: {"name": t.name, "spoils": t.spoils, "unspoilable": t.unspoilable, "help": t.help}
            for t in TILE_TYPES.values()}

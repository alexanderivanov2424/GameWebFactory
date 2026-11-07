"""Block Blast: symbols. A symbol sits on a tile (tiles.py) and does something when its cell is
cleared; what each one does is in effects.py (EFFECTS, one function per symbol).

    SYMBOLS        {name: code}   in display/log order; codes are one uppercase letter, used in card
                                  files' "symbols" rows and in the client state
    DECORATIVE     names of symbols that are only art and do nothing (the goblin face: the
                   goblin *tile* is what spoils lines, see tiles.py); left out of card counts
    BY_CODE        {code: name}
    public_table() {code: name} for the game state

Adding a symbol: a code here, its effect function in effects.py, and an icon + `.sym-<name>`
style in the client (SYMBOL_ICONS in game.js, index.html). Any tile type can carry it.
"""

SYMBOLS = {
    "coin": "C",
    "attack": "A",
    "shield": "S",
    "chapel": "R",
    "siege": "E",
    "goblin": "G",  # decorative: drawn on goblin tiles, no effect
}
DECORATIVE = {"goblin"}
BY_CODE = {code: name for name, code in SYMBOLS.items()}


def public_table():
    return dict(BY_CODE)

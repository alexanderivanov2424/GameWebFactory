"""Block Blast: loading the card files (cards/shapes/ and the starting deck) when the game is imported.
The market's card packs are in packs.py.

A card places tiles (tiles.py), some carrying symbols (symbols.py). Fields are documented in
cards/README.md. Bad files are logged (logger "block-blast") and skipped. Loaders take a
folder or file so tests can feed them temporary files.

    CARDS          {id: card}, card = {
                       "id", "name",
                       "cost":    gold to buy it in the Cost Market (market/cost.py)
                       "tile":    the card's main tile type (what "#" means; colours the card)
                       "playOn":  "self" or "opponent" (whose board the card goes on)
                       "loose":   tiles need not touch
                       "exile":   leaves its owner's deck for good once played (not when patched)
                       "symbols": {symbol name: count} (art-only symbols left out)
                       "pieces":  4 pieces (board.py), turned clockwise 0-3 quarter turns (never
                                  mirrored), each [(dr, dc, tile, symbol), ...]
                       "sizes":   [(height, width)] of each rotation }
    public(card)   what clients get: name, cost, tile, playOn, exile, symbols, rotations (board.layers)
    STARTING_DECK  {card id: copies}   cards/starting-deck.json
    parse_counts(data, cards, where)   {card id: copies} from JSON (packs.py uses it too)
    rotate(piece, height, width)       one clockwise quarter turn -> (piece, height, width)
    rotations(piece, height, width)    all 4 -> (pieces, sizes)
    deck_ids(counts)                   [card id, ...] with each id repeated `copies` times
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json, load_json_dir, text, whole

from . import effects, symbols, tiles
from .board import EMPTY, layers

log = logging.getLogger("block-blast")

CARDS_DIR = Path(__file__).resolve().parent.parent / "cards"
MAX_SIZE = 5  # cards fit in 5x5
CARD_TILE = "#"  # in a card's "tiles" rows: a tile of the card's own "tile" type
PLAY_ON = ("self", "opponent")
MAX_COPIES = 20
MAX_COST = 30


def rotate(piece, height, width):
    """One quarter turn clockwise: the cell at (r, c) moves to (c, height - 1 - r)."""
    return [(dc, height - 1 - dr, tile, symbol) for dr, dc, tile, symbol in piece], width, height


def connected(piece):
    cells = {(dr, dc) for dr, dc, _, _ in piece}
    seen, todo = set(), [next(iter(cells))]
    while todo:
        r, c = todo.pop()
        if (r, c) in seen:
            continue
        seen.add((r, c))
        todo += [n for n in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)) if n in cells]
    return seen == cells


def _grid(data, key, height=None, width=None):
    rows = data.get(key)
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SIZE or not all(isinstance(r, str) for r in rows):
        raise ValueError(f"{key} must be a list of 1 to {MAX_SIZE} strings")
    if not 1 <= len(rows[0]) <= MAX_SIZE or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError(f"{key} rows must all have the same length, 1 to {MAX_SIZE}")
    if height is not None and (len(rows), len(rows[0])) != (height, width):
        raise ValueError(f"{key} must be the same size as tiles ({height}x{width})")
    return rows


def _piece(tile_rows, symbol_rows, tile):
    """The card's cells as a piece (board.py), from its two grids; `#` is `tile`."""
    piece = []
    for r, (tile_row, symbol_row) in enumerate(zip(tile_rows, symbol_rows)):
        for c, (t, s) in enumerate(zip(tile_row, symbol_row)):
            if t == EMPTY:
                if s != EMPTY:
                    raise ValueError(f"symbol {s!r} at row {r + 1}, column {c + 1} has no tile under it")
                continue
            if t == CARD_TILE:
                cell_tile = tile
            elif t in tiles.BY_CODE:
                cell_tile = tiles.BY_CODE[t].name
            else:
                raise ValueError(f"tiles may only use {EMPTY!r}, {CARD_TILE!r} and {sorted(tiles.BY_CODE)}")
            if s != EMPTY and s not in symbols.BY_CODE:
                raise ValueError(f"symbols may only use {EMPTY!r} and {sorted(symbols.BY_CODE)}")
            piece.append((r, c, cell_tile, symbols.BY_CODE[s].name if s != EMPTY else None))
    if not piece:
        raise ValueError("needs at least one tile")
    return piece


def rotations(piece, height, width):
    """The 4 clockwise rotations (0-3 quarter turns) -> (pieces, sizes)."""
    pieces, sizes = [piece], [(height, width)]
    for _ in range(3):
        turned, h, w = rotate(pieces[-1], *sizes[-1])
        pieces.append(turned)
        sizes.append((h, w))
    return pieces, sizes


def symbol_counts(piece):
    """{symbol name: count} in symbols.SYMBOLS order, leaving out art-only symbols (whose effect
    is the no-op effects.decorative)."""
    counts = {}
    for _, _, _, name in piece:
        if name and effects.EFFECTS[name] is not effects.decorative:
            counts[name] = counts.get(name, 0) + 1
    return {name: counts[name] for name in symbols.SYMBOLS if name in counts}


def parse_card(card_id, data):
    tile = data.get("tile", tiles.DEFAULT_TILE)
    if tile not in tiles.TILE_TYPES:
        raise ValueError(f"tile must be one of {sorted(tiles.TILE_TYPES)}")
    play_on = data.get("playOn", "self")
    if play_on not in PLAY_ON:
        raise ValueError(f"playOn must be one of {PLAY_ON}")
    tile_rows = _grid(data, "tiles")
    height, width = len(tile_rows), len(tile_rows[0])
    symbol_rows = _grid(data, "symbols", height, width) if "symbols" in data else [EMPTY * width] * height
    piece = _piece(tile_rows, symbol_rows, tile)
    loose = flag(data, "loose")
    if not loose and not connected(piece):
        raise ValueError('tiles must all touch (one piece), or "loose": true')
    pieces, sizes = rotations(piece, height, width)
    return {
        "id": card_id,
        "name": text(data, "name", 30, required=True),
        "cost": whole(data, "cost", 0, MAX_COST),
        "tile": tile,
        "playOn": play_on,
        "loose": loose,
        "exile": flag(data, "exile"),
        "symbols": symbol_counts(piece),
        "pieces": pieces,
        "sizes": sizes,
    }


def public(card):
    return {
        "name": card["name"],
        "cost": card["cost"],
        "tile": card["tile"],
        "playOn": card["playOn"],
        "exile": card["exile"],
        "symbols": card["symbols"],
        "rotations": [
            layers({(dr, dc): (t, s) for dr, dc, t, s in piece}, h, w)
            for piece, (h, w) in zip(card["pieces"], card["sizes"])
        ],
    }


def load_cards(folder):
    return load_json_dir(folder, parse_card, log)


def parse_counts(data, cards, where):
    """{card id: copies} from JSON; unknown cards and bad counts are logged (as `where`) and skipped."""
    if not isinstance(data, dict):
        raise ValueError("must be a JSON object of card id -> copies")
    counts = {}
    for card_id, copies in data.items():
        if card_id not in cards:
            log.error("%s: unknown card %r skipped", where, card_id)
        elif type(copies) is not int or not 0 <= copies <= MAX_COPIES:
            log.error("%s: copies of %r must be 0 to %d", where, card_id, MAX_COPIES)
        elif copies:
            counts[card_id] = copies
    return counts


def load_counts(path, cards):
    return load_json(path, lambda data: parse_counts(data, cards, path), log, default={})


def deck_ids(counts):
    return [card_id for card_id, copies in counts.items() for _ in range(copies)]


CARDS = load_cards(CARDS_DIR / "shapes")
STARTING_DECK = load_counts(CARDS_DIR / "starting-deck.json", CARDS)

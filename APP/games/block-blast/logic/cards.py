"""Block Blast: loading the card files (cards/ next to server.py) when the game is imported.

A card places tiles (tiles.py), some carrying symbols (symbols.py). Fields are documented in
cards/README.md. Bad files are logged (logger "block-blast") and skipped. Loaders take a
folder or file so tests can feed them temporary files.

    CARDS          {id: card}, card = {
                       "id", "name",
                       "tile":    the card's main tile type (what "#" means; colours the card)
                       "playOn":  "self" or "opponent" (whose board the card goes on)
                       "loose":   tiles need not touch
                       "exile":   leaves its owner's deck for good once played (not when patched)
                       "symbols": {symbol name: count} (decorative symbols left out)
                       "pieces":  4 pieces (board.py), turned clockwise 0-3 quarter turns (never
                                  mirrored), each [(dr, dc, tile, symbol), ...]
                       "sizes":   [(height, width)] of each rotation }
    public(card)   what clients get: name, tile, playOn, exile, symbols, rotations (board.layers)
    STARTING_DECK  {card id: copies}   cards/starting-deck.json
    BONUS_DECK     {card id: copies}   cards/bonus-deck.json
    rotate(piece, height, width)       one clockwise quarter turn -> (piece, height, width)
    deck_ids(counts)                   [card id, ...] with each id repeated `copies` times
"""

import logging
from pathlib import Path

from gamekit.data import flag, load_json, load_json_dir, text

from . import symbols, tiles
from .board import EMPTY, layers

log = logging.getLogger("block-blast")

CARDS_DIR = Path(__file__).resolve().parent.parent / "cards"
MAX_SIZE = 5  # cards fit in 5x5
CARD_TILE = "#"  # in a card's "tiles" rows: a tile of the card's own "tile" type
PLAY_ON = ("self", "opponent")
MAX_COPIES = 20


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
    piece = []
    for r in range(height):
        for c in range(width):
            t, s = tile_rows[r][c], symbol_rows[r][c]
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
            piece.append((r, c, cell_tile, symbols.BY_CODE.get(s)))
    if not piece:
        raise ValueError("needs at least one tile")
    loose = flag(data, "loose")
    if not loose and not connected(piece):
        raise ValueError('tiles must all touch (one piece), or "loose": true')
    pieces, sizes = [piece], [(height, width)]
    for _ in range(3):
        turned, h, w = rotate(pieces[-1], *sizes[-1])
        pieces.append(turned)
        sizes.append((h, w))
    counts = {}
    for _, _, _, symbol in piece:
        if symbol and symbol not in symbols.DECORATIVE:
            counts[symbol] = counts.get(symbol, 0) + 1
    return {
        "id": card_id,
        "name": text(data, "name", 30, required=True),
        "tile": tile,
        "playOn": play_on,
        "loose": loose,
        "exile": flag(data, "exile"),
        "symbols": {name: counts[name] for name in symbols.SYMBOLS if name in counts},
        "pieces": pieces,
        "sizes": sizes,
    }


def public(card):
    return {
        "name": card["name"],
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


def load_counts(path, cards):
    def parse(data):
        if not isinstance(data, dict):
            raise ValueError("must be a JSON object of card id -> copies")
        counts = {}
        for card_id, copies in data.items():
            if card_id not in cards:
                log.error("%s: unknown card %r skipped", path, card_id)
            elif type(copies) is not int or not 0 <= copies <= MAX_COPIES:
                log.error("%s: copies of %r must be 0 to %d", path, card_id, MAX_COPIES)
            elif copies:
                counts[card_id] = copies
        return counts

    return load_json(path, parse, log, default={})


def deck_ids(counts):
    return [card_id for card_id, copies in counts.items() for _ in range(copies)]


CARDS = load_cards(CARDS_DIR / "shapes")
STARTING_DECK = load_counts(CARDS_DIR / "starting-deck.json", CARDS)
BONUS_DECK = load_counts(CARDS_DIR / "bonus-deck.json", CARDS)

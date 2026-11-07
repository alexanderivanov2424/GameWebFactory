# Block Blast cards

Loaded by `logic/cards.py` when the game is imported. Bad files are logged (logger
"block-blast") and skipped, so one broken card never takes the game down.

## Tiles and symbols
A card places **tiles**, and any tile may carry a **symbol**. They are separate ideas:
- **Tile types** (`logic/tiles.py`) decide how a tile behaves on the board:
  `b` blue (plain), `g` grey (goblins can't spoil it), `x` goblin, the purple tile (a cleared
  row or column holding one has no effect).
- **Symbols** (`logic/symbols.py`, effects in `logic/effects.py`) do something when their cell
  is cleared: `C` coin (+1 gold), `A` attack (1 damage to your target, plus your strength once
  per attack; shields absorb it first), `S` shield (+1 shield), `R` chapel (+1 card removal),
  `E` siege (every 3 give +1 strength), `G` goblin face (art only: does nothing by itself; the
  goblin cards draw it on their purple tiles).

Any symbol can sit on any tile type.

## `shapes/<id>.json`: one file per card
The file name (lowercase letters, digits, `-`, `_`) is the card id.

```json
{
  "name": "Hook",
  "tiles":   ["#.", "#.", "##"],
  "symbols": ["..", "..", "A."]
}
```

- `name`: shown on the card (up to 30 characters).
- `tiles`: rows of equal length, at most 5×5. `.` is no tile, `#` is a tile of the card's
  `tile` type, and a tile code (`b`, `g`, `x`) is a tile of that type (for cards that mix types).
- `symbols` (optional): the same size as `tiles`; `.` or a symbol code on top of a tile.
- `tile` (optional, default `"blue"`): the card's main tile type, what `#` means. It also
  colours the card (`.card-<tile>` in `client/index.html`).
- `playOn` (optional, default `"self"`): `"opponent"` puts the card on an opponent's board (goblins).
- `loose` (optional): `true` lets the tiles sit apart; otherwise they must touch edge to edge.
- `exile` (optional): `true` removes the card from its owner's deck once played (shown with
  🗑). Patching it for a 1×1 tile still discards it normally.

Players may rotate a card by quarter turns but never mirror it, so an L and a J are different
cards. The client draws any card from the definitions in the game state, so a new card needs no code.

Adding a tile type: a `TileType` in `logic/tiles.py` (flags `spoils` / `unspoilable`, or a new
flag read in `logic/effects.py`) and a `.tile-<name>` style in `client/index.html`.
Adding a symbol: a `Symbol` in `logic/symbols.py`, its function in `EFFECTS` (`logic/effects.py`),
and an icon (`SYMBOL_ICONS` in `client/draw.js`) plus a `.sym-<name>` style.

## `starting-deck.json` and `bonus-deck.json`
`{card id: copies}`: each player's starting deck, and the bonus deck the bank is dealt from.
Unknown ids are logged and skipped.

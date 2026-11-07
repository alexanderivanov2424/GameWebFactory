# Block Blast: developer notes

Rules and the message list: the docstring at the top of `server.py`. Card files and their
fields: `cards/README.md`.
Tests: `tests/` (`python3 -I tools/run_tests.py block-blast`).

## Read this game to learn
- **Shapes on a grid with rotation but no mirroring**: `logic/cards.py` precomputes the 4
  clockwise rotations of each shape at load time and sends them in `game.cards`, so the client
  draws the selected rotation and the ghost without any geometry rules of its own. Placement
  is "rotation index + top-left corner"; `logic/board.py` checks and applies it.
- **Line clears**: full rows and columns clear together; a crossing cell counts once
  (`board.clear` works on a set of cells).
- **A personal deck per player** with `gamekit.Deck`: hand = drawn instances, played cards go
  to `deck.discard`, bought cards are new instances made by the buyer's own deck
  (`deck.add`), so uids never clash between players.
- **A conveyor market** (`logic/bank.py`): price = slot index + 1; one buy per turn (`BUYS_PER_TURN` in
  `match.py`, counted in `Match.buys`, sent as `buysLeft`); the bought slot stays `None` until
  `refill()` at the end of the turn (or when the current player leaves).
- **Hover ghost on a board**: `BlockBlastBoard` (`client/board.js`) toggles classes on the 81
  existing cells (`ghost`, `bad`, `gsym gsym-<symbol>` + `data-ghost`, `would-clear`) through
  `clearPreview` / `showGhost`; `updateGhost()` in `game.js` decides what to show. The board is
  rebuilt only on a new state. Rotate with R, right-click or the wheel; the cell under the mouse
  is the shape's middle (`placement()`).
- **Who may act when lives in one place**: `Match.require_turn` (current player only) and
  `Match.require_in` (any time while still in: `aim`, `remove_card`). `server.py` has no turn
  check of its own; it only type-checks fields, dispatches, then `check_over()` after every action.
- **Aiming**: a per-player target, changeable off-turn, re-aimed automatically when the target is
  knocked out or leaves.
- **Tiles and symbols are separate** (the model to extend): a board cell is `(tile, symbol)`
  (`logic/board.py`); tile types and their behaviour flags are in `logic/tiles.py` (`TileType`:
  `spoils` for goblin, the purple tile; `unspoilable` for grey); symbols are `Symbol`s in
  `logic/symbols.py` (the 👺 on goblin tiles is art only: its effect is the no-op
  `effects.decorative`, which also leaves it out of card counts), with one effect function each in `logic/effects.py` (`EFFECTS`). Card files give a `tiles` grid (`#` = the card's `tile` type,
  or a tile code) and a `symbols` overlay. Clients get boards and rotations as two layers of
  one-letter codes plus the code tables (`game.tileTypes`, `game.symbolTypes`); the client draws
  the tile as the cell background (`.tile-<name>`) and the symbol as a rounded square on top
  (`.sym-<name>`, icons in `SYMBOL_ICONS` in `client/draw.js`). A new tile type or symbol is a registry entry, a
  style and (for new behaviour) code in `effects.py`; see `cards/README.md`.
- **Cards played onto someone else's board**: `playOn: "opponent"` cards (goblins) go on an
  opponent's board (`place` with `board`; the message's `"player"`). `Match.resolve_clears(owner)`
  runs for the board's owner; lines holding a `spoils` tile are spoiled (no effect), but a symbol
  still counts through a crossing unspoiled line, or when its own tile is `unspoilable`.
  Client: every board is interactive; `dropsOn(pid)` decides where the selected card may go,
  and the ghost works on any board.
- **Card flags** in the JSON: `playOn`, `loose` (tiles need not touch) and `exile` (the card
  leaves its owner's deck once played: `put_down(..., exile=True)` skips the discard; a patch
  still discards). The client shows 🗑 on exile cards. Goblin and siege cards are exile.
- **Siege and strength**: siege symbols (on grey tiles on the siege cards); `seat.siege`
  counts towards `SIEGE_PER_STRENGTH` (3, `effects.py`), carrying the remainder; `strength` is
  added once to the damage of each clear that has attack symbols (`Clear.damage`), using
  the strength from before the current clear.
- **Rules pure, orchestration in Match**: `effects.py` works on one board and one `Seat`
  (`clear_lines` -> `Cleared`, `apply_symbols` -> `Clear`, `deal_damage`) and never sees the
  Match; `Match.resolve_clears` picks the target, writes the log and `lastClear`, and knocks out.
  Test new effects on those functions directly (`PureEffectTests`).
- **Shield and card removal resources**: shield absorbs damage point for point and decays by 1
  in `next_turn` for the player whose turn starts; chapel tokens are spent with `remove`
  (any time) on a hand card, which leaves the deck without being discarded.

## Map
- `server.py`: `SETTINGS` (health), `ACTIONS` and thin `on_*` wrappers that
  type-check (`whole_number`, strict ranges) and call `Match`; `on_game_message` dispatches, then
  `check_over()`.
- `logic/match.py`: `Match`: setup, who may act (`require_turn` / `require_in`), `place` / `patch`
  (both via `put_down`, then `resolve_clears`), `buy`, `aim`, `remove_card`, `end_turn` ->
  `next_turn` (bank refill, shield decay), `knock_out`, `leave`, `public` (the unchanging part,
  `static_state()`, is built once into `self.catalog`), `private`. Log entries are
  `{step, pid, text}`; `lastClear` drives the client's flash.
- `logic/seat.py`: `Seat` dataclass (board, health, gold, shield, chapels, siege, strength,
  target, out, left, deck, hand), `hand_card(uid)`, `public()`, `private()`.
- `logic/effects.py`: `clear_lines` (spoiling, counting symbols), `EFFECTS` / `apply_symbols`,
  `deal_damage`. No Match, no log.
- `logic/tiles.py`, `logic/symbols.py`: the registries (`TileType`, `Symbol`: names, codes, flags).
- `logic/board.py`: board of `(tile, symbol)` cells; `fits`, `place`, `full_lines`, `clear`,
  `layers` / `public` (the two-layer client form).
- `logic/bank.py`: `Bank` (bonus deck as a `Deck` that only shrinks, 5 slots).
- `logic/cards.py`: loaders (`parse_card` -> `_grid`, `_piece`, `rotations`, `symbol_counts`) and
  `CARDS` (`pieces` = 4 rotations, `public(card)` for clients), `STARTING_DECK`, `BONUS_DECK`.
- `client/draw.js` (`BlockBlastDraw`): pure drawing from layers + the catalog (`state.game`):
  `tileEl`, `symbolEl`, `miniShape`, `cardFace`, `SYMBOL_ICONS`.
- `client/board.js` (`BlockBlastBoard`): `build` (one board's cells, `--size` from
  `rules.boardSize`, hover/click/rotate handlers), `placement`, `clearPreview`, `showGhost`
  (ghost + would-clear), `flash`. No page state.
- `client/game.js` (the page): `renderGame()` -> `renderBoards` (`seatPanel`: name, ♥ health,
  💰 gold, 🛡 shield, ✝ removals, tags, aim button, board), `renderBank`, `renderLog`,
  `renderHand` (fixed bottom bar; a Delete button under each card while you have removals);
  selection state (`selection`, `hover`) with `checkSelection()` dropping it when the turn
  passes; `dropsOn(pid)`, `currentPiece()` (a patch is `rules.patch`), the hint text;
  `flashClear()` animates `lastClear` once (not on the first render after a reload).
  The "Auto end turn" switch under End turn is client-only (sessionStorage `block-blast:autoEnd`):
  `maybeAutoEnd()` runs after every game render and sends `end_turn` once per `turnNumber`
  when your hand is empty and no bank card is affordable (`canBuy()`), after a 600 ms pause
  that re-checks everything.
- `tests/`: `helpers.py` (shared fixtures: `new_match`, `give`, one-letter board cells; imported
  as `games.block-blast.tests.helpers`), `test_rules.py` (Match: setup, placing, clearing, aim,
  bank, turns, leaving, state views), `test_effects.py` (shields, chapels, goblins, siege, and
  `effects.py` on its own), `test_lobby.py` (Sim), `test_cards.py` (registries, loader, files).

## Pitfalls seen here
- `one_of(x, (0, 1, 2, 3))` accepts `True` (it equals 1): rotation and uids go through
  `whole_number`, which checks `type(x) is int`.
- State size: card definitions (4 rotations x 2 layers) are most of the ~15 KB state sent after
  every change (FullState). Fine for this site; switch to `PatchState` if it grows a lot.
- The hover ghost used to assume your own board (`mainCells`); with goblins it is per board
  (`hover.pid`, `boardCells`, `boardEls`), so keep new previews board-agnostic.
- Client constants come from `game.rules` (`boardSize`, `handSize`, `buysPerTurn`,
  `siegePerStrength`, `patch`); don't copy them into JS. The 3x3 guide lines in index.html's
  `nth-child(9n+...)` are the one place that still assumes a 9x9 board.
- `Match.public()` shares `self.catalog`'s dicts across calls: never mutate the returned state.
- Bank cards come from the bank's own `Deck`; giving the buyer that instance would mix uid
  spaces. `buy` adds a fresh instance with the buyer's `deck.add(card_id)`.
- A knock-out or a leave on the current player's own turn must still refill the bank and pass
  the turn (`knock_out` calls `next_turn` before removing them from the queue).

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
- **Hover ghost on a board**: `updateGhost()` in `client/game.js` toggles classes on the 81
  existing cells (`ghost`, `bad`, `gsym gsym-<symbol>` + `data-ghost`, `would-clear`); the board is rebuilt only on a
  new state. Rotate with R, right-click or the wheel; the cell under the mouse is the shape's
  middle (`placement()`).
- **Aiming**: a per-player target, changeable off-turn (`ANY_TIME` in `server.py` lists the
  actions that skip the turn check), re-aimed automatically when the target is knocked out or leaves.
- **Tiles and symbols are separate** (the model to extend): a board cell is `(tile, symbol)`
  (`logic/board.py`); tile types and their behaviour flags are in `logic/tiles.py` (`spoils`:
  goblin, the purple tile; `unspoilable`: grey); the 👺 on goblin tiles is a decorative symbol
  (`symbols.DECORATIVE`, a no-op in `EFFECTS`, left out of card counts); symbols are in `logic/symbols.py` with one effect function each in
  `logic/effects.py` (`EFFECTS`). Card files give a `tiles` grid (`#` = the card's `tile` type,
  or a tile code) and a `symbols` overlay. Clients get boards and rotations as two layers of
  one-letter codes plus the code tables (`game.tileTypes`, `game.symbolTypes`); the client draws
  the tile as the cell background (`.tile-<name>`) and the symbol as a rounded square on top
  (`.sym-<name>`, icons in `SYMBOL_ICONS`). A new tile type or symbol is a registry entry, a
  style and (for new behaviour) code in `effects.py`; see `cards/README.md`.
- **Cards played onto someone else's board**: `playOn: "opponent"` cards (goblins) go on an
  opponent's board (`place` with `board`; the message's `"player"`). `resolve_clears(owner)`
  runs for the board's owner; lines holding a `spoils` tile are spoiled (no effect), but a symbol
  still counts through a crossing unspoiled line, or when its own tile is `unspoilable`.
  Client: every board is interactive; `dropsOn(pid)` decides where the selected card may go,
  and the ghost works on any board.
- **Card flags** in the JSON: `playOn`, `loose` (tiles need not touch) and `exile` (the card
  leaves its owner's deck once played: `put_down(..., exile=True)` skips the discard; a patch
  still discards). The client shows 🗑 on exile cards. Goblin and siege cards are exile.
- **Siege and strength**: siege symbols (on grey tiles on the siege cards); `seat["siege"]`
  counts towards `SIEGE_PER_STRENGTH` (3, `effects.py`), carrying the remainder; `strength` is
  added once to the damage of each clear that has attack symbols (`attacks + strength`), using
  the strength from before the current clear.
- **Shield and card removal resources**: shield absorbs damage point for point and decays by 1
  in `next_turn` for the player whose turn starts; chapel tokens are spent with `remove`
  (any time) on a hand card, which leaves the deck without being discarded.

## Map
- `server.py`: `SETTINGS` (health), `ACTIONS` and thin `on_*` wrappers that
  type-check (`whole_number`, strict ranges) and call `Match`.
- `logic/match.py`: `Match`: setup, `place` / `patch` (both via `put_down`, then
  `resolve_clears` in `effects.py`), `buy`, `aim`,
  `remove_card`, `end_turn` -> `next_turn` (bank refill, shield decay),
  `remove`, `public`, `private`. Log entries are `{step, pid, text}`; `lastClear` drives the
  client's flash.
- `logic/effects.py`: `resolve_clears` (spoiling, counting symbols, `EFFECTS`, `deal_attack`,
  log line, `last_clear`, knock-out).
- `logic/tiles.py`, `logic/symbols.py`: the registries (names, codes, behaviour flags).
- `logic/board.py`: board of `(tile, symbol)` cells; `fits`, `place`, `full_lines`, `clear`,
  `layers` / `public` (the two-layer client form).
- `logic/bank.py`: `Bank` (bonus deck as a `Deck` that only shrinks, 5 slots).
- `logic/cards.py`: loaders and `CARDS` (`pieces` = 4 rotations, `public(card)` for clients),
  `STARTING_DECK`, `BONUS_DECK`.
- `client/game.js`: `renderGame()` -> `renderBoards` (`seatPanel`: name, ♥ health, 💰 gold,
  🛡 shield, ✝ removals, tags, aim button, board), `renderBank`, `renderLog`, `renderHand`
  (fixed bottom bar; a Delete button under each card while you have removals);
  selection state (`selection`, `hover`) with `checkSelection()` dropping it when the turn
  passes; `flashClear()` animates `lastClear` once (not on the first render after a reload).
  The "Auto end turn" switch under End turn is client-only (sessionStorage `block-blast:autoEnd`):
  `maybeAutoEnd()` runs after every game render and sends `end_turn` once per `turnNumber`
  when your hand is empty and no bank card is affordable (`canBuy()`), after a 600 ms pause
  that re-checks everything.
- `tests/test_block_blast.py` (Match rules + Sim lobby tests), `tests/test_cards.py`.

## Pitfalls seen here
- `one_of(x, (0, 1, 2, 3))` accepts `True` (it equals 1): rotation and uids go through
  `whole_number`, which checks `type(x) is int`.
- State size: card definitions (4 rotations x 2 layers) are most of the ~15 KB state sent after
  every change (FullState). Fine for this site; switch to `PatchState` if it grows a lot.
- The hover ghost used to assume your own board (`mainCells`); with goblins it is per board
  (`hover.pid`, `boardCells`, `boardEls`), so keep new previews board-agnostic.
- Bank cards come from the bank's own `Deck`; giving the buyer that instance would mix uid
  spaces. `buy` adds a fresh instance with the buyer's `deck.add(card_id)`.
- A knock-out or a leave on the current player's own turn must still refill the bank and pass
  the turn (`knock_out` calls `next_turn` before removing them from the queue).

# Block Blast: developer notes

Rules and the message list: the docstring at the top of `server.py`. Card files and their
fields: `cards/README.md`.
Tests: `tests/` (`python3 -I tools/run_tests.py block-blast`).

## Read this game to learn
- **Shapes on a grid with rotation but no mirroring**: `logic/cards.py` precomputes the 4
  clockwise rotations of each shape at load time (`gamekit.shapes.rotations`) and sends them in `game.cards`, so the client
  draws the selected rotation and the ghost without any geometry rules of its own. Placement
  is "rotation index + top-left corner"; `logic/board.py` checks and applies it.
- **Line clears**: full rows and columns clear together; a crossing cell counts once
  (`board.clear` works on a set of cells).
- **A personal deck per player** with `gamekit.Deck`: hand = drawn instances, played cards go
  to `deck.discard`, bought cards are new instances made by the buyer's own deck
  (`deck.add`), so uids never clash between players.
- **Swappable market types** (`logic/market/`): the shared card pool is a `Market` subclass
  picked by a lobby setting. `Market` (base.py) owns the slots dealt from the bonus deck,
  `take` and `public()`; a type overrides `price(slot)` and `refill()` and declares `KEY`,
  `LABEL`, `RULES`, `CAN_REMOVE` and its size setting (`SIZE_SETTING`, `DEFAULT_SIZE`,
  `MAX_SIZE`). `server.py`'s `market_settings()` builds the settings from the `MARKETS`
  registry: a `Choice` of types (gamekit) plus one `Int` size per type. Match uses only the
  base API, and the client draws any type from `game.market` (`slots` with `price`,
  `canRemove`).
  - Conveyor Market (`conveyor.py`): price = slot index + 1; the bought slot stays `None`
    until `refill()` at the end of the turn (or when the current player leaves), which shifts
    cards towards slot 0.
  - Cost Market (`cost.py`): price = the card file's `cost`; `market_remove` takes a card out
    of the game instead of buying; empty slots refill in place.
  One buy per turn either way (`BUYS_PER_TURN` in `match.py`, counted in `Match.buys` (a
  removal counts), sent as `buysLeft`; `Match.market_card` holds the checks buying and
  removing share).
- **Card packs picked in the lobby** (`logic/packs.py`, `cards/packs/`): one JSON file per pack
  of bonus cards; `server.py` builds a gamekit `MultiChoice` ("packs", checkboxes, at least 1,
  all by default) from `PACKS`, and `Match` deals the market from `pool(settings["packs"])`. A
  new pack is a new file; no code.
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
  style and (for new behaviour) code in `effects.py`; see `cards/README.md`. Each also has a
  legend line for the client's help window (`?`): `TileType.help`, and `effects.HELP` for symbols
  (sent as `tileTypes[code].help` and `game.symbolHelp`).
- **Deck view**: `seats[pid].deck` is everything a player owns (hand + draw + discard, from
  `Seat.card_ids()`), sorted by cost then name in `Match.deck_list` so it never reveals which card
  is where; the client's Deck button on each seat panel shows it in a window, grouped as ×n.
- **Cards played onto someone else's board**: `playOn: "opponent"` cards (goblins) go on an
  opponent's board (`place` with `board`; the message's `"player"`). `Match.resolve_clears(owner)`
  runs for the board's owner; lines holding a `spoils` tile are spoiled (no effect), but a symbol
  still counts through a crossing unspoiled line, or when its own tile is `unspoilable`.
  Client: every board is interactive; `dropsOn(pid)` decides where the selected card may go,
  and the ghost works on any board.
- **Card flags** in the JSON: `playOn` and `exile` (the card
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
  `next_turn` (market refill, shield decay), `knock_out`, `leave`, `public` (the unchanging part,
  `static_state()`, is built once into `self.catalog`), `private`. Log entries are
  `{step, pid, text}`; `lastClear` drives the client's flash.
- `logic/seat.py`: `Seat` dataclass (board, health, gold, shield, chapels, siege, strength,
  target, out, left, deck, hand), `hand_card(uid)`, `public()`, `private()`.
- `logic/effects.py`: `clear_lines` (spoiling, counting symbols), `EFFECTS` / `apply_symbols`,
  `deal_damage`. No Match, no log.
- `logic/tiles.py`, `logic/symbols.py`: the registries (`TileType`, `Symbol`: names, codes, flags).
- `logic/board.py`: board of `(tile, symbol)` cells; `fits`, `place`, `full_lines`, `clear`,
  `layers` / `public` (the two-layer client form).
- `logic/market/`: `__init__.py` (`MARKETS`, `DEFAULT`, `MAX_SIZE`, `make`), `base.py`
  (`Market`: bonus deck as a `Deck` that only shrinks, slots, `take`, `public`), `conveyor.py`
  (`ConveyorMarket`), `cost.py` (`CostMarket`).
- `logic/cards.py`: loaders (`parse_card` -> `_grid`, `_piece`, `rotations`, `symbol_counts`) and
  `CARDS` (`pieces` = 4 rotations, `public(card)` for clients), `STARTING_DECK`, `parse_counts`.
- `logic/packs.py`: `PACKS` (from `cards/packs/*.json`), `pool(selected, packs)`: the market's
  bonus deck from the host's packs.
- `client/draw.js` (`BlockBlastDraw`): pure drawing from layers + the catalog (`state.game`):
  `tileEl`, `symbolEl`, `miniShape`, `cardFace`, `SYMBOL_ICONS`.
- `client/board.js` (`BlockBlastBoard`): `build` (one board's cells, `--size` from
  `rules.boardSize`, hover/click/rotate handlers), `placement`, `clearPreview`, `showGhost`
  (ghost + would-clear), `flash`. No page state.
- `client/game.js` (the page): `renderGame()` -> `renderBoards` (`seatPanel`: name, ♥ health,
  💰 gold, 🛡 shield, ✝ removals, tags, aim button, board), `renderMarket` (Buy, plus Remove when `canRemove`), `renderLog`,
  `renderHand` (fixed bottom bar; a Delete button under each card while you have removals);
  windows (native `<dialog>`s in index.html): `renderDeckWindow` (the 🂠 Deck button on each seat
  panel; re-rendered while open) and `renderHelp` (the ? button, kept above the hand bar by a
  ResizeObserver); the keyboard shortcuts are off while a window is open;
  selection state (`selection`, `hover`) with `checkSelection()` dropping it when the turn
  passes; `dropsOn(pid)`, `currentPiece()` (a patch is `rules.patch`), the hint text;
  `flashClear()` animates `lastClear` once (not on the first render after a reload).
  The "Auto end turn" switch under End turn is client-only (sessionStorage `block-blast:autoEnd`):
  `maybeAutoEnd()` runs after every game render and sends `end_turn` once per `turnNumber`
  when your hand is empty and no market card is affordable (`canBuy()`), after a 600 ms pause
  that re-checks everything.
- `tests/`: `helpers.py` (shared fixtures: `new_match`, `give`, one-letter board cells; imported
  as `games.block-blast.tests.helpers`), `test_rules.py` (Match: setup, placing, clearing, aim,
  turns, leaving, state views), `test_market.py` (both types, buy/remove, the settings),
  `test_packs.py` (loader, pool, the setting), `test_effects.py` (shields, chapels, goblins, siege, and
  `effects.py` on its own), `test_lobby.py` (Sim), `test_cards.py` (registries, loader, rotations).
  Tests check behaviour (what an ability does: a goblin in a cleared row stops its attack
  counting, etc.), never card content: cards are added, removed and rebalanced all the time,
  so no checks of how many cards/packs there are, a card's cost, symbols, shape or pack.
  Compute sizes (`helpers.pool_size()`, `helpers.starting_size()`) or use fixture
  cards/packs (e.g. a tiny pack passed as `Match(..., packs=...)`). Ask the user before
  adding any new test.

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
- The market's size is a setting, so `server.py` only bounds `slot` by `market.MAX_SIZE`;
  `Match.market_card` checks it against the actual market. A new market type also needs a
  `RULES` line and its size range; the lobby rules paragraph in index.html describes each type.
- A small pool (e.g. only siege cards: 3) leaves market slots empty for the whole game; that's
  allowed, not an error.
- Every card file needs a `cost` (the loader skips cards without one), even starter cards that
  never reach the market.
- Market cards come from the market's own `Deck`; giving the buyer that instance would mix uid
  spaces. `buy` adds a fresh instance with the buyer's `deck.add(card_id)`.
- A knock-out or a leave on the current player's own turn must still refill the market and pass
  the turn (`knock_out` calls `next_turn` before removing them from the queue).

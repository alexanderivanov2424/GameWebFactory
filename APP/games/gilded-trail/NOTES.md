# Gilded Trail: developer notes

Rules and the message list: the docstring at the top of `server.py`. Cards: `cards/*.json`
(fields in `logic/content.py`); map presets: `maps/*.json` (fields in `logic/board.py`).
Tests: `tests/` (`python3 -I tools/run_tests.py gilded-trail`).

A deck-building race on the rules of a well-known jungle race game (base game), with
original names, maps and look. Card name map, for whoever compares rules:
Explorer→Porter, Traveler→Trader, Sailor→Boatman, Scout→Tracker, Trailblazer→Bushwhacker,
Pioneer→Vanguard, Giant Machete→Great Cleaver, Captain→Riverboat, Photographer→Sketch Artist,
Journalist→Chronicler, Treasure Chest→Gold Cache, Millionaire→Patron,
Jack-of-all-Trades→Handyman, Adventurer→Wayfarer, Prop Plane→Airship, Transmitter→Courier,
Cartographer→Surveyor, Compass→Star Chart, Scientist→Naturalist, Travel Log→Field Journal,
Native→Local Guide.

## Read this game to learn
- **A hex map** generated on the server from a seed (`logic/board.py`: axial "q,r" keys, a
  chain of radius-3 tiles, Voronoi-style terrain patches, connectivity checks) and drawn as
  SVG (`client/board.js`). Preset maps are JSON files with a fixed seed; the random map takes
  its seed from a host setting.
- **Deck-building with a shared market** (`logic/market.py`): 6 slots plus a reserve that
  opens when a slot sells out; one `gamekit.Deck` per player; hand kept across turns.
- **Pending choices inside a turn**: an action card sets `match.pending`, which blocks every
  other action until its follow-up message (trash / take / guide) arrives.
- The server sends the client every legal step (`private.options`: per explorer, per hex, the
  requirement, which hand cards can pay it and whether the current card can go on) and each
  card's coin value, so the client has no movement or buying rules.

## Map
- `server.py`: `SETTINGS` (map `Choice` built from `maps/`, random-map length and seed),
  `ACTIONS`, thin `on_*` wrappers that type-check messages and call `Match`.
- `logic/match.py`: `Match`: setup (seats, decks, explorers), helpers used by the other
  modules (`hand_card`, `take_from_hand`, `use_card`, `draw`, `add_log`), turn flow
  (`end_turn` → `next_turn`: round end, final round, `MAX_ROUNDS`), `remove`, `end` + `rank`
  (tie-break), `public`, `private`.
- `logic/movement.py`: `requirement`, `move` (movement cards, the current card going on),
  `pay` (rubble, base camps, rubble blockades), `guide`, `claim`, `place` (arrival),
  `options` / `guide_targets` for the client.
- `logic/actions.py`: `buy`, `play`, and the pending follow-ups `trash`, `take`, `guide`.
- `logic/market.py`, `logic/board.py`, `logic/content.py`: market, map, content loaders.
- `client/board.js`: `TrailBoard.create(...)`: `draw(game)` rebuilds the SVG when the state
  changes; `highlight(...)` only toggles classes ("go" = this click acts now, "step" = legal
  but needs a card or a choice).
- `client/game.js`: `renderGame()` calls `renderResult`, `renderStatus`, `renderPrompt`
  (side panel: the current choice), `renderPeople`, `renderLog`, `renderMarket` (market +
  reserve below the map), `renderHand` (fixed bottom bar with Buy / End turn). Modes:
  `explorer`, `cardSel`, `mode` (pay / buy / end / play) and `picks`, reset each turn.
- `tests/`: `test_content.py` (files, boards), `test_rules.py` (Match, one rule per test),
  `test_lobby.py` (Sim), `helpers.py` (fixtures).

## Rule decisions (where the published rules are unclear)
- Clearing a blockade doesn't move the explorer; the paying card may go on with its leftover
  value. The Local Guide may take a blockade (without moving) instead of stepping.
- Single-use cards leave the game only when used for their function: a movement step or
  blockade, an action, or full coin value (Gold Cache, Airship) when buying. Spent as ½ coin
  or discarded for rubble, they go to the discard pile.
- The Courier's free card isn't a purchase: any card with copies left, market or reserve, and
  it never moves a reserve card into an empty slot.
- Tie-break: most blockades, then the highest single blockade, then who arrived first.
- Star Chart (Compass) costs 2; card costs come from memory of the published game and may
  need tuning.

## Pitfalls seen here
- PatchState: no `None` in the state. Arrived explorers are `""`, sold-out market slots are
  `""`, and `turn` / `moving` / `pending` are left out when absent.
- The round ends when every remaining player's `TurnQueue` value is equal (everyone has had
  as many turns); re-check that after a player leaves, or a final round never ends.
- A movement card stays bound to the explorer it started moving: the other explorer needs a
  new card (one card never moves two explorers).

# Bastion 2: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files and their
fields: `content/README.md`. The user's original spec: `DESIGN_PROMPT.md`.
Tests: `tests/` (`python3 -I tools/run_tests.py bastion2`); none yet (see "Proposed tests").

History: a new game next to `bastion` (2026-11-10), not a replacement. Same idea (each player
grows their own city on a shared map) but deck-building instead of worker placement: no units on
tiles, no terrain, an unbounded grid. Enemies are hidden for now (work in progress): nothing
here knows about them. `bastion`'s dormant `logic/foes.py`, `attacks.py`, `combat.py`,
`enemies.py` and `content/enemies/` are the starting point when they come back (they need
rewiring to seats either way).

## Read this game to learn
- **Deck-building with a play area and per-turn counters** (`seat.py`, `effects.py`): resource
  cards move from the hand to `Seat.play` and add to `Seat.temp`; costs can mix temporary
  resources, permanent food and per-turn population (`Seat.missing` / `pay` / `refund`).
- **Cards that punish being discarded** (upkeep: `effects.discard`): one function handles every
  way a card leaves the hand unplayed (end of turn, paying another card by discarding).
- **Temporary card instances** (`inst["temp"]`): made by actions, vanish instead of being
  discarded; they never count as owned (`views.owned_cards`).
- **Pending placements that complete at end of turn**: on the board as `pending` (public,
  reserving the tile), paid at once, refundable (`unbuild`) until the turn ends.
- **An unbounded board**: `Board.bounds()` (structures + MARGIN) is what's drawn and where
  the camera may go; `client/map.js` pans/zooms a transformed world and clamps the view centre.
- **A full-screen game page with a HUD around the edges** (`client/index.html`):
  `body.in-game` hides `<main>` (except the error banner) and shows the fixed `#game` layer.
- **Turn mode as a setting**: "together" (each seat has `done`; the round ends when all are
  done) or "order" (`Match.turn_index`); both share `end_turn` and `turn_reason`.

## Map
- `server.py`: the Turns setting, `ACTIONS`, type checks (`cell` allows negative coordinates up
  to `board.LIMIT`, `uids`), thin wrappers. `SYNC = PatchState`.
- `logic/match.py`: `Match` (constants `HAND_SIZE`, `BUY_ACTIONS`, `START_FOOD`,
  `SETUP_PIECES`, `COLORS`): setup, `start_play`, `begin_turn`, `buy`, `end_turn`, `advance`,
  `leave`, `turn_reason` / `acting` (who may act), `note` (the chronicle).
- `logic/effects.py`: `play` (resource / action / upkeep / structure), `play_reason`, `build`,
  `unbuild`, `choose`, `use` / `use_reason` / `bundle`, `apply`, `discard`, `lose_population`,
  `complete`, `food_cap`, `actions_per_turn`.
- `logic/board.py`, `logic/seat.py`, `logic/market.py`, `logic/content.py`, `logic/views.py`:
  see `logic/__init__.py`.
- `client/map.js` (`Bastion2Map`: ground, structures, pulsing spots, ghost, hover, camera),
  `client/hud.js` (`Bastion2Hud`: card faces, city, structure actions, market, players,
  chronicle, play area, actions circle, deck window), `client/game.js` (controller: selection
  modes, hand clicks, prompt line, End turn with 📌 kept cards); see their headers.

## Adding content
- A card or structure is one JSON file (`content/README.md`); the client renders any of them from
  the catalog without code changes. New effect *kinds* go in `logic/content.py`
  (`parse_effect`, `effect_text`) and `logic/effects.py` (`apply`).
- A new temporary resource: add it to `content/resources.json` with `"temporary": true`; the
  play area grows a counter for it.

## Pitfalls seen here
- Castles must be inside the shown bounds and `CASTLE_GAP` from other cities, so `MARGIN` must
  stay larger than `CASTLE_GAP` or the second castle has nowhere to go.
- Build spots count only *built* structures, so taking back a pending build never strands
  another pending one.
- Setup pieces give their population but not their `on_build` cards (the starting deck has them).
- PatchState: no `None` in dicts; cells are `"x,y"` strings; the chronicle is a dict keyed by
  index plus `logCount`.

## Proposed tests (not added: the user approves tests first)
- Rules (Match): castle gap and bounds; build spots only next to built structures; paying a
  structure (temporary + population) and the refund on unbuild; upkeep pay vs discard; each
  upkeep penalty on discard (add card / lose population and a Villager); bundle (one resource,
  exact value, cards leave the deck); temporary cards vanish; food capped by storage; end of turn
  (kept cards stay, draw 5, builds complete with optional cards skipped); both turn modes and
  leaving mid-turn.
- Lobby (Sim): hands hidden from others and spectators; acting out of turn is refused.

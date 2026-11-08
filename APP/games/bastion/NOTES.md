# Bastion: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files and their
fields: `content/README.md`. Tests: `tests/` (`python3 -I tools/run_tests.py bastion`).

Rebuilt on 2026-11-08 from player feedback: it used to be a tower-defense game (sieges simulated
on the server and replayed). That version is in git history (before this change), if a pattern
from it is ever needed (deterministic simulation sent as a compact replay).

## Read this game to learn
- **Co-op with simultaneous turns**: no `TurnQueue`; every seat has a `done` flag, anyone acts
  at any time during a round, and `Match.check_all_done()` ends the round once every remaining
  seat is done. A leave re-runs it. "Done" can be taken back until the last player finishes;
  a done player can't act (take it back first).
- **Adjacency-driven buildings from data**: each structure file lists `requires` and `bonuses`
  as `{"near": X, ...}` conditions; `Board.near()` counts terrain cells, empty grass, road/wall
  tiles or distinct buildings of a kind, and `economy.output()` turns that into an amount with a
  breakdown (`parts`) the inspector shows. A new interaction is a line of JSON, no code.
- **Polyomino placement with rotation** via `gamekit.shapes` (shared with block-blast): rotations
  are precomputed at load; placement is "rotation + top-left cell". The client puts the shape's
  middle under the mouse (`anchor()` in game.js).
- **Server-computed targets**: `views.private()` sends, per hand card, every legal top-left cell
  per rotation with the output the building would have there (blueprints; cached by
  `board.version`), or every building the card may work/repair/cure with a preview text. The
  client's ghost, outlines and tips need no rules.
- **Cards made from other content**: every structure file yields a blueprint `plan-<id>` and,
  if it works, a crew card `crew-<id>` (`cards.structure_cards`).
- **Enemies as cards with cycling attacks** (`foes.py`, `attacks.py`): attack parts are generic
  (steal, ruin, keep, place blights, curse cards into decks, plague, freeze, kill), and each
  enemy has its own `defeat` ways (soldiers, resources, cures, paying off its curses, razing its
  lair), so a new enemy is usually just JSON.
- **Card instances with extra fields**: curse cards an enemy adds carry `"from": enemy index`
  on the Deck instance, so paying one off can hurt its sender.

## Map
- `server.py`: settings (difficulty, keep health, map from `MAPS`, enemies, peaceful rounds,
  rounds between enemies), `ACTIONS`, thin wrappers (`cell()`), `check_over()` after every
  action. `SYNC = PatchState`.
- `logic/match.py`: `Match` (constants at the top: `HAND_SIZE`, `START_STOCK`, `OVERTIME`,
  `COLORS`): `start_round` (reset worked flags, arrivals, refill hands), `end_turn` /
  `check_all_done` -> `end_round` (income, attacks, loss checks), `play` -> `build` / `action` /
  curse payment, `work`, `cure`, `strike`, `raze`, `hurt` (beaten: its blights and plague go;
  all beaten wins), `buy`, `leave`, `end`.
- `logic/views.py`: `public` (catalog cached on the match: `kinds`, `cards`, `icons`, terrain),
  `private` + `build_targets` / `action_targets`.
- `logic/board.py`: `Structure` (uid, kind, cells, owner, ruined, plague, frozen, worked, store),
  `Board` (placement `check` / `place`, `near`, `link` / `road_reach`, `protected`,
  `raid_targets`, `ruin` / `repair`, blights, `public`).
- `logic/economy.py`: `output`, `why_not`, `work`, `haul`, `repair_cost`, `STORE_CAP`.
- `logic/foes.py`, `logic/attacks.py`, `logic/seat.py`, `logic/market.py`,
  `logic/structures.py`, `logic/cards.py`, `logic/enemies.py`, `logic/maps.py`: see
  `logic/__init__.py`.
- `client/board.js` (`BastionBoard`): the grid (terrain, roads, walls, blights, buildings with
  merged borders, owner stripe, output/store/flag badges), mouse events, hover marks.
- `client/game.js`: status bar, enemy cards (strike buttons), hover (ghost / outlines / tips),
  inspector, market, team, chronicle, hand bar, deck window.
- `tests/`: `helpers.py` (`FixtureCase` installs small fixture structures, cards and enemies,
  parsed by the real loaders, into the shared registries per test; an 8x6 `MAP`; `new_match`,
  `give`, `build`, `foe`), `test_board.py` (placement, rotation, near, links, raids),
  `test_economy.py` (output, delivery, haul, who can work), `test_cards.py` (playing every kind
  of card, market, done flag), `test_foes.py` (arrival, attacks, defeat ways, win/loss, leaving),
  `test_lobby.py` (Sim, real content). Tests never check real content numbers.

## Pitfalls seen here
- The public state mixes the catalog and the board: the catalog's structure files are `kinds`,
  because `structures` is the board's buildings (an early version clashed).
- PatchState: no `None` in dicts. Catalog views drop None fields (`structures.public`,
  `cards.public`); structure views use `""` / `false`.
- Shapes whose rotations coincide (a domino turned twice) give identical target maps; harmless.
- Numbers (costs, prices, outputs, enemy health, peaceful rounds) are a first pass reasoned from
  the economy, not tuned by play. Rough budget: ~1 gold per player per round from Tax plus the
  keep's 1; soldiers cost 1 food + 1 tool (2 wood) per 2 at a barracks; tier-1 enemies have
  3-4 health x1.5 for 2 players.

# Bastion: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files and their
fields: `content/README.md`. Tests: `tests/` (`python3 -I tools/run_tests.py bastion`).

History: rebuilt on 2026-11-08 from player feedback (it used to be a tower-defense game with
sieges simulated on the server and replayed), then on 2026-11-09 into worker placement (v3):
people from houses become units placed on buildings, Hauling or enemies, then resolved in turn
order. The v2 version (crew/Villagers/haul cards, carriages moving along roads, everyone acting
at once with `done` flags) is in git history before that change.

## Read this game to learn
- **Worker placement with a simultaneous place phase and a sequential act phase**
  (`units.py`, `Match.ready` / `end_turn`): `Match.phase` is `"place"` (everyone places at once,
  `ready` flags that can be taken back until the last one confirms) or `"act"` (one player at a
  time: `Match.order` is the seat order rotated so this round's first player leads,
  `Match.turn_index` walks it). No `TurnQueue`: one pass per round with a rotating start is a
  list and an index. `Match.placing(pid)` / `Match.acting(pid)` are the guards every message goes
  through.
- **Targets as strings** (`"s<uid>"`, `"haul"`, `"fight<i>"`, `"raze<x>,<y>"`): the same key
  is the message field, the `Match.placed` key and the public `placements` key. `units.parse`
  turns one into the thing it names; `units.clear_gone` drops placements whose target vanished
  (a beaten enemy, a razed tile; units there are lost).
- **Population and upkeep** (`food.py`): structures carry `population`; the end of a round eats
  the cheapest bread/wheat mix that covers everyone (a tiny brute force over the bread count);
  the hungry don't become units next round.
- **Adjacency-driven buildings from data**: each structure file lists `requires` and `bonuses`
  as `{"near": X, ...}` conditions; `Board.near()` counts terrain cells, empty grass, road/wall
  tiles or distinct buildings of a kind, and `economy.output()` turns that into an amount with a
  breakdown (`parts`) the inspector shows. A new interaction is a line of JSON, no code. Farms
  cluster with `{"near": "farm", "each": 1}`.
- **Polyomino placement with rotation** via `gamekit.shapes` (shared with block-blast): rotations
  are precomputed at load; placement is "rotation + top-left cell". The client puts the shape's
  middle under the mouse (`anchor()` in game.js).
- **Server-computed targets and previews**: `views.private()` sends, per blueprint in hand,
  every legal top-left cell per rotation with the output the building would have there (cached
  by `board.version`), per repair/cure card every building it may go on, per unit target a
  preview (`places`: text, text with a tool, and why it can't resolve right now), and the haul
  `sources`. The client needs no rules.
- **Strikes that carry over** (`combat.py`): a fighting unit is 1 strike on `foe.strikes`; every
  `defeat.soldiers` strikes are 1 damage. Blights keep their own `strikes` toward their raze cost.
  The soldier counter's Strike / raze spend the remainder.
- **Board pieces bought without cards** (`tiles.py`): road and wall tiles are 1x1, placed one at a
  time from team stocks bought in batches; removal is free. Their legal cells go in the public
  state (`tiles`, cached by `board.version`).
- **Market bundles**: a blueprint's `bundle` copies go to the buyer's discard pile at once.
- **Market redealt every round, plus a paid reroll** whose price climbs within a round
  (`Match.rerolls`, `REROLL_COST` in `market.py`); `rerollCost` reaches the client in the state.
- **A card that picks other hand cards** (Absolution, `trash`): the play message lists their uids
  in `remove`; the client has a pick mode in the hand bar with a confirm button.
- **Card instances with extra fields**: curse cards an enemy adds carry `"from": enemy index`
  on the Deck instance, so paying one off can hurt its sender.
- **Enemies as cards with cycling attacks** (`foes.py`, `attacks.py`): attack parts are generic
  (steal, loot stores, ruin, keep, place blights, curse cards into decks, plague, freeze, kill),
  and each enemy has its own `defeat` ways, so a new enemy is usually just JSON.

## Map
- `server.py`: settings (difficulty, keep health, map from `MAPS`, enemies, peaceful rounds,
  rounds between enemies), `ACTIONS`, thin wrappers (`cell()`, `target()`, `flag()`),
  `check_over()` after every action. `SYNC = PatchState`.
- `logic/match.py`: `Match` (constants at the top: `HAND_SIZE`, `START_STOCK`, `FIRST_CARD`,
  `OVERTIME`, `COLORS`): `start_round` (resets, arrivals, hands, first player, `units.hand_out`),
  `ready` / `check_all_ready` (-> act), `end_turn` / `next_turn` -> `end_round` (income, upkeep,
  attacks, loss checks), guards `placing` / `acting` / `turn()`, `pay`, `buy` (bundles),
  `reroll`, `leave`, `end`; wrappers for units, playing, combat, tiles.
- `logic/units.py`: `hand_out`, `parse`, `place_reason` / `targets`, `place` / `unplace` /
  `drop` / `lose` / `clear_gone`, `resolve_reason` / `resolve` -> `work` / `haul` /
  `combat.unit_fight` / `combat.unit_raze`, `free`, `mine`, `preview`.
- `logic/food.py`: `population`, `feed` (preview), `upkeep`, `FEEDS`.
- `logic/hauling.py`: `carriages`, `capacity`, `queue`, `sources`, `best_source`, `why_not`,
  `take`, `SMALL` / `BIG`.
- `logic/playing.py`: `play` -> `build` / curse payment / `action` (`trashed`).
- `logic/combat.py`: `strike`, `raze`, `unit_fight`, `unit_raze`, `raze_cost`, `hurt`, `cure`.
- `logic/views.py`: `public` (catalog cached on the match: `kinds`, `cards`, `icons`, terrain,
  rule numbers), `placements`, `private` + `build_targets` / `action_targets` / `places`.
- `logic/board.py`: `Structure` (uid, kind, cells, ruined, plague, frozen, worked, store),
  `Board` (placement `check` / `place`: buildings may replace roads, `near`, `link` /
  `road_reach`, `protected`, `raid_targets`, `loot_targets`, `ruin` / `repair`, blights (with
  `strikes`), `public`).
- `logic/economy.py`: `output`, `amount` (+ tool), `blocked` (placement), `why_not` (resolving),
  `work`, `preview`, `repair_cost`, `STORE_CAP`, `TOOL_BOOST`.
- `logic/tiles.py`, `logic/foes.py`, `logic/attacks.py`, `logic/seat.py`, `logic/market.py`,
  `logic/structures.py`, `logic/cards.py`, `logic/enemies.py`, `logic/maps.py`: see
  `logic/__init__.py`.
- `client/board.js` (`BastionBoard`: the grid, unit tokens), `client/panels.js` (status bar,
  round bar with the Hauling pool, enemy cards with Fighting pools, market, chronicle, card
  faces, inspector) and `client/game.js` (controller: state, unit clicks incl. Shift+click on a
  pool = all free units / all your fighters, board hover, bottom bar, windows); see their headers.
- `tests/`: `helpers.py` (`FixtureCase` installs small fixture structures, cards and enemies,
  parsed by the real loaders, into the shared registries per test; an 8x6 `MAP`; `new_match`
  (act=True: everyone ready, p1's turn), `give`, `build`, `foe`, `units`, `put`, `ready_all`,
  `next_round`), `test_board.py` (placement, rotation, near, links, raids), `test_economy.py`
  (output, delivery, who can work), `test_cards.py` (blueprints, units working, repair/cure,
  curses, market, whose turn), `test_foes.py` (arrival, attacks, defeat ways, win/loss, turns,
  ready, leaving), `test_lobby.py` (Sim, real content). Tests never check real content numbers.
  `bots.py` and `playtest.py` are the playtest harness (not collected as tests; see "Playtest
  bots" below).

## Playtest bots
The user asked for bots to balance the game (an exception to CLAUDE.md's no-bots rule, for
playtesting only). They live in `tests/` (never deployed) under names the test runner doesn't
collect:
- `tests/bots.py`: `Bot(match, pid, rng, stats, style)` plays through the Match API only
  (`units.targets` / `resolve_reason`, `hauling.sources`, `board.check` + `economy.output` for
  build spots, `tiles`, Match methods). `"good"`: greedy placement over a value per output (food
  worth more when the stockpile won't cover the next rounds, scarce materials more than
  plentiful ones, a strike on an active enemy about 2.6 goods), work before hauls before input
  users, a tool on the best work when there are spares, blueprints at the best-scoring spot
  (output, link, neighbours, not cutting roads), roads to link what's cut off, a market want
  list driven by food margin, materials, idle units and enemies, houses only while food and
  work keep up. `"passive"`: works the farm and lumbermill, fights with the rest, never builds
  or buys.
- `tests/playtest.py`: runs whole games in parallel processes and prints aggregate stats.
  From the Dev folder (`/T` in the pod):
  `python3 -I APP/games/bastion/tests/playtest.py [--games 50] [--players 1-4] [--map valley|highlands]
  [--difficulty normal] [--bot good|passive] [--seed 1] [--all] [--verbose] [--trace] [--jobs N]`.
  `--all` runs 1-3 players on both maps; `--trace --games 1 --seed S` prints a line per round
  (hands, stockpile, placements, enemies, buildings). 50 one-player games take ~12 s on 4 cores;
  three-player games are ~4x slower.
- Targets (good bot, normal, default settings): win ~65-85% on both maps for 1-3 players, the
  keep usually hurt, ~10 houses (population 20+) late but not early, some hungry rounds, goods
  hauled every mid-game round, tools used; the passive bot loses.

Results at the end of the 2026-11-09 tuning (50 games each, seeds 1-50, good bot, normal,
keep 20, 5 enemies, 5 peaceful rounds, gap 3; houses/population at rounds 10 / 15 / end):

| players, map | win | lost: keep / overtime | houses r10 / r15 / end | pop end | keep end | hungry rounds | hauled / round | tools used |
|---|---|---|---|---|---|---|---|---|
| 1p valley | 76% | 7 / 5 | 6.2 / 8.2 / 11.4 | 25 | 7.6 | 2.5 | 4.2 | 12 |
| 2p valley | 82% | 4 / 5 | 8.6 / 11.2 / 16.9 | 36 | 13.3 | 1.5 | 5.5 | 19 |
| 3p valley | 74% | 6 / 7 | 10.0 / 13.5 / 20.3 | 43 | 11.9 | 1.6 | 6.1 | 20 |
| 1p highlands | 76% | 7 / 5 | 5.6 / 7.8 / 10.9 | 24 | 9.3 | 1.1 | 5.4 | 8 |
| 2p highlands | 80% | 6 / 4 | 7.7 / 11.0 / 16.6 | 35 | 12.6 | 1.7 | 4.8 | 15 |
| 3p highlands | 74% | 3 / 10 | 9.2 / 13.7 / 21.5 | 45 | 13.6 | 1.1 | 7.5 | 16 |

Games last 22 rounds on average (the boss arrives on round 18). Enemies stay 3-6 rounds each
(the Rat King ~9: it can only be hurt as fast as it plagues). The passive bot loses every game
(30 games each, 1p and 2p valley, 1p highlands: the keep falls around round 20).

## Balance budget (after the 2026-11-09 playtest)
- People and food: the start's 4 people eat 2 wheat; the keep makes 1 wheat (its own 2 people
  never starve, so a famine can't lock the city at 0 units), so one worked lone farm balances
  the start and every house (2 people) needs 1 more wheat a round. A farm makes 1, +1 per farm
  next to it (max +2), +1 by water: 3-4 in a cluster (6-8 people per unit). A bakery turns 1
  wheat into 1 bread, 2 next to a farm (8 people): the better food building once farms exist.
- Materials: a lumbermill makes 2-4 wood, a quarry 2-4 (base 2, +1 next to 3 mountains, +1 next
  to a storage yard). A house costs 1 wood + 1 stone; its blueprint comes 3 for 2 gold, farms
  3 for 2 gold. Wood is the tighter material (everything uses it, the Frost Witch eats it).
- Gold: the keep's 2 a round (~40 a game) plus Tax (2, and an Unrest that costs 1 wheat), Sell
  (1 tool -> 3) and markets (2-6 per unit). A 1p game spends ~65 on blueprints, ~20 on
  rerolls, ~6 on roads. Start: 4 gold, 6 wood, 4 stone, 6 wheat, 2 tools.
- Units: one per person fed; 1 player has ~14 at round 10 and ~21 at round 20. From the first
  enemy on, about half of all unit actions are fights.
- Enemies (strikes for 1 player; x(1 + 0.5 per extra player), x0.75/1/1.3 by difficulty): tier 1
  Goblins and Wolves 20, Rat King 4 cures; tier 2 Bandit Lord 16 x 2 soldiers (or its Ransom
  Notes), Frost Witch 6 x 2 wood, Siege Ogre 40, Necromancer 4 altar tiles x 3; bosses Dragon
  36 x 2 and Orc Warlord 34 x 2 (+ war camps). Keep attacks 1-5; the boss and tier 2 all hit the
  keep in their cycle. A chapel heals 1 (+1 per house next to it, max 2, +1 with a garden) for
  1 gold. Enemy hp files allow at most 50 (`enemies.py`): bosses use 2 soldiers per damage.

## Pitfalls seen here
- The public state mixes the catalog and the board: the catalog's structure files are `kinds`,
  because `structures` is the board's buildings (an early version clashed).
- PatchState: no `None` in dicts. Catalog views drop None fields (`structures.public`,
  `cards.public`); structure views use `""` / `false`; `turn` and `firstPlayer` are `""` when
  nobody; `places[...].why` / `.tool` are `""` when empty.
- Placements aren't board state: `board.version` doesn't change when units move, so nothing
  cached by it may depend on `Match.placed`.
- A player's own action can change whose turn it is (leaving, a last end_turn ends the round):
  `Match.leave` adjusts `turn_index` and may end the round; check `match.result` before
  stepping on in loops.
- Shapes whose rotations coincide (a domino turned twice) give identical target maps; harmless.
- Building over roads: a road whose tiles a building covers is gone, which can cut the network
  (and links, hence hauling) apart.
- Starting-town entries in the maps must fit the current shapes: changing a shape can silently
  drop a start building (logged "doesn't fit"); check both maps after a shape change (build a
  `Board(MAPS[id], log)` and look for the error).
- Numbers were tuned by bot playtests (2026-11-09; "Playtest bots" below). After changing
  content or a constant, rerun `playtest.py --all` and compare with the table there.
- A keep hemmed in on all four sides (buildings over its road cells) cuts every road link: the
  start town leaves only two road cells next to the keep, so new depots (storage yards) are how
  a city grows outward.

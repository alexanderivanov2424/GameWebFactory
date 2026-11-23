# Snowbound: developer notes

Rules and the message list: the docstring at the top of `server.py`. Modules: `logic/__init__.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py snowbound`).

## Read this game to learn
- A `RealtimeGame` where each player walks a character (WASD as realtime input, collision with
  tile walls) and the camera follows them, with **client-side prediction**: `client/grid.js`
  mirrors `logic/avatars.py` `blocked()`/`move()` exactly and the client corrects toward the
  server's position (snap when far, drift when standing still).
- A full-screen canvas game page with a HUD over it (`client/index.html` + `hud.js`): fixed
  boxes kept clear of the site's GWF/Settings buttons (top corners) and the chat tab (bottom right).
- An idle/incremental economy (machines whose price grows 15% per copy) where **every machine kind
  behaves differently** (`logic/machines.py`, one function per kind behind `STEPS`) on top of a
  shared unit core (`logic/units.py`: claims, local-then-budgeted global target search, `work()`).
  Upgrades are mostly behaviour flags checked by id (`Player.has`, `Match.team_has`).
- Area-of-interest sync: hundreds of units would be too much per tick, so each player's
  `private_state` only carries the units within `view.VIEW` lots of their character.
- A very large grid (up to 384 x 384) over `Snapshots` as three dirty-row string layers (snow,
  features, road levels), drawn as one pixel per lot on an offscreen canvas, plus per-lot details
  only for the visible window.
- A small factory game on top: digging machines carry their snow to drop points (`logic/hauling.py`),
  processors turn it into goods and pull from neighbours (`logic/factory.py`), sleds sell goods at a
  market, and everyone routes over a player-built road network (`logic/roads.py`).
- **Incremental pathing on a big grid**: `roads.Field` keeps "cost to the nearest drop point" for
  every road lot. Roads only get added or faster, so costs only drop: changes are relaxed with a
  persistent heap and a per-tick budget instead of re-running Dijkstra. Trips go straight to a road
  lot within `ACCESS`, then follow `next` pointers (or straight, if cheaper).
- Hidden one-of-a-kind landmarks (`logic/landmarks.py`, `landmarks/*.json`) that reward whoever
  clears their last lot with a unique machine (`"unique": true`, never in the shop), a unique
  building or a team effect.

## Map
- `machines/*.json`, `upgrades/*.json`, `goods/*.json`, `landmarks/*.json`: content (schema in
  `logic/content.py`'s docstring). Processor recipes are in their machine file.
- `logic/match.py`: `Match.step(dt)` order: weather -> once a second (blizzard snowfall or
  deliveries) -> golden snowflakes (caught by walking into them) -> `survival.step` ->
  `avatars.step` (walking, held-down shoveling) -> `roads.Network.update` (route fields) ->
  `units.step` (hauling trips run before a machine's own step) -> beams -> goal. Actions, huts,
  placed machines, Shovel Buddy boost (`shovel()`), finds.
- `logic/world.py`: lots, `targets`, `dig()` (workable lots) and `melt()` (any lot), roads,
  dusting, `nearest_target(..., ok=filter)`, row strings.
- `logic/hauling.py`: trips home / back, unloading, Snow Depots. `logic/roads.py`: levels, `lay()`,
  route fields. `logic/factory.py`: processors and sleds. `logic/uniques.py`: landmark helpers.
  `logic/landmarks.py`: placement, rewards, team effects (`Match.effects`).
- `logic/economy.py`: `Player`. `logic/survival.py`: weather, heat sources (cabin, huts,
  braziers), food/warmth, deliveries. `logic/view.py`: the client contract.
- `client/`: `game.js` wiring, `grid.js` rows + walking rules, `view.js` canvas, `input.js`
  controls + prediction + the road tool, `hud.js` HUD (road tool box, depot button).

## Pitfalls seen here
- Lot index 0 is a real lot: never write `nearest_target(...) or fallback`.
- The economy is finite: all money comes from snow, about the map's total snow (Large at 75% is
  roughly $100M). Keep prices below what a map can pay out.
- Full scans of `world.targets` or the grid inside a per-unit step are too slow with hundreds of
  units: use the local search, the `SEARCHES_PER_TICK` budget, or a counter (`road_count`).
- `units.step` iterates a copy of the units: finds (rescued skiers) add units mid-step.
- Keyboard handlers must ignore typing in the chat, which lives in shadow DOM: check
  `ev.composedPath()[0]`, not `ev.target`.
- `AppDom.el` assigns props with `Object.assign`: use `className`, not `class`. A CSS `display`
  rule on a class overrides the `hidden` attribute: add `[hidden] { display: none }`.
- Machine speed/reach/collision changes on the server must be mirrored in `client/grid.js`
  (`move` rules are sent in `state.game.move`, including walk speed per road level).
- The team owns everything: cash, earned, diesel, rations, machine counts (`owned`) and upgrades live
  in `economy.Stores` (`Match.stores`); `Player.cash`, `.owned`, `.upgrades`... are properties onto it,
  so any Player gives the same rates, prices and upgrade checks. Never loop over players to add up
  team values (diesel use, deliveries): do it once (`Match.diesel_use()`). `unit.pid` is only the
  buyer (log credit, colour); units outlive their buyer, so machine code gets the buyer's Player or
  any player. One rally point (`Match.rally_spot`); Shovel Buddies follow `units.buddy_leaders()`.
  Processors and sleds serve everyone (no owner checks).
- Pay machine snow through `units.collect()`, never `player.earn()`: hauling machines must carry it.
  The player's own shovel is still paid at once.
- Route fields assume roads are never removed or downgraded and drop points never go away. If
  that ever changes, the fields need a full rebuild (costs can only go down incrementally).
- Landmark lots are kind `"site"`: nothing can be built on them (placed rewards take the centre lot).
- Unique machines still count in `Player.owned` (so their rate and diesel count) but are hidden
  from the shop and refused by `buy_machine`.

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
- A very large grid (up to 384 x 384) over `Snapshots` as two dirty-row string layers, drawn as
  one pixel per lot on an offscreen canvas, plus per-lot details only for the visible window.

## Map
- `machines/*.json`, `upgrades/*.json`: content (schema in `logic/content.py`'s docstring).
- `logic/match.py`: `Match.step(dt)` order: weather -> once a second (blizzard snowfall or
  deliveries) -> golden snowflakes (caught by walking into them) -> `survival.step` ->
  `avatars.step` (walking, held-down shoveling) -> `units.step` -> beams -> goal. Actions, huts,
  placed machines, Shovel Buddy boost (`shovel()`), finds.
- `logic/world.py`: lots, `targets`, `dig()` (workable lots) and `melt()` (any lot), roads,
  dusting, `nearest_target(..., ok=filter)`, row strings.
- `logic/economy.py`: `Player`. `logic/survival.py`: weather, heat sources (cabin, huts,
  braziers), food/warmth, deliveries. `logic/view.py`: the client contract.
- `client/`: `game.js` wiring, `grid.js` rows + walking rules, `view.js` canvas, `input.js`
  controls + prediction, `hud.js` HUD.

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
  (`move` rules are sent in `state.game.move`).

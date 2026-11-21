# Snowbound: developer notes

Rules and the message list: the docstring at the top of `server.py`. Modules: `logic/__init__.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py snowbound`).

## Read this game to learn
- A `RealtimeGame` idle/incremental game (Cookie Clicker style): clicks as rate-limited ACTIONS
  (a per-player click budget refilled each tick), machines whose price grows 15% per copy,
  generated x2 tier upgrades per machine (from the machine JSON), and shared team upgrades
  bought once for everyone.
- A very large grid (up to 384 x 384 lots) over `Snapshots`: two row-string layers (snow level,
  feature) rebuilt only for dirty rows, so a tick's delta only carries rows that changed. The
  client decodes them into one pixel per lot on an offscreen canvas and scales it up with
  smoothing off, so drawing the whole map costs one `drawImage`.
- Autonomous units without pathfinding: one crew per player and machine kind, claiming the
  nearest workable lot (local search first, full scan only when nothing is near).
- Light survival on top of an economy: a shared stove/woodpile, personal food and warmth with
  automatic eating, upkeep (diesel), and weather that blocks purchases.

## Map
- `machines/*.json`, `upgrades/*.json`: content (schema in `logic/content.py`'s docstring).
- `logic/match.py`: `Match.step(dt)` order: weather -> once a second (blizzard snowfall or
  deliveries) -> golden snowflakes -> `survival.step` -> `crews.step` -> click budgets -> goal.
  Actions (click, catch_flake, buy, upgrade, supply, set_focus) and `found()` (what a lot hid).
- `logic/world.py`: lots, `targets` (workable lots), `dig()` (the only place a lot is cleared),
  `dust()`, `nearest_target()`, row strings.
- `logic/economy.py`: `Player` (wallet, machines, upgrades, needs, rates, click power).
- `logic/crews.py`: crews (targeting, driving, digging). `logic/survival.py`: weather, stove,
  food/warmth, blizzard snowfall, deliveries. `logic/view.py`: the client contract.
- `client/map.js`: canvas (lots, cabin, crews interpolated with `rt.sample`, cursors, focus
  flags, golden snowflake, blizzard veil) and mouse/keys. `client/game.js`: lobby wiring and the
  side panels (refreshed 4x a second; buttons updated in place).

## Pitfalls seen here
- Lot index 0 is a real lot: never write `nearest_target(...) or fallback` (see `crews._first`).
- The economy is finite: all money comes from snow (plus finds), about the map's total snow.
  Machine and upgrade prices must stay below what a map can pay out (Large at 75% is roughly
  $100M), or the top machines can never be bought. Check this when adding machines or maps.
- `AppDom.el` assigns props with `Object.assign`: use `className`, not `class`.
- The lobby itself answers spectators ("You're not playing right now.") and sends an empty
  room back to the lobby, so the game needs no code for either.

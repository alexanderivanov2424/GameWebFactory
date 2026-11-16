# Hex Realms: developer notes

Rules and messages: `server.py`'s docstring. Resolution order and score: `logic/match.py`'s header.
Content: `structures/`, `units/`, `advances/` (one JSON per item; fields in `logic/content.py`).
Player-facing text: `client/text.js`. Tests: `python3 -I tools/run_tests.py hex-realms`.

## Patterns worth copying
- **Secret simultaneous orders.** Orders live in `Match.orders[pid]` (private state), are paid when given
  and refunded on cancel or failure. Public stock is a start-of-turn snapshot (`Match.shown`) so spending
  doesn't leak plans. Any order clears your `done`.
- **Simultaneous movement** (`movement.py`): paths fixed at order time, every unit steps one cell at a
  time; swaps, shared targets, followers and blocks are handled in a fixed order. Fighting stops both units.
  Own units hop over each other.
- **Dice combat** (`combat.py`): every roll is in the event so the client can replay it. Tests use
  `helpers.FixedDice`.
- **Fog of war as private state** (`vision.py`): the public state has no map; each member's private `view`
  holds what they see. Planning checks use only what the player knows; resolution uses the truth. The client
  merges `view` into `game`, so the rest of the page reads `game.cells` / `game.units`.
- **Forecast = resolution.** `economy.report` is both the planning forecast and what `end_of_turn` applies
  (`resolving=True`), so the numbers players see are the numbers they get. `report.flows` breaks it down
  per structure / unit / site / bought cell for the client's resource view (`map.setResView`).
- **Data-driven content.** Structures' output (`produce`, `onTerrain`, `perCell`, `perAdjacent` by terrain / unique types /
  type / tag; terrain only counts unbuilt cells), `boost` (+n to what adjacent own structures of a type / tag
  make, while the booster works), `freeNear` (no workers while touching a terrain: `economy.jobs`), tags,
  housing, storage, trade rates; advances' dice `effect`s, per-type output `bonus` and
  per-tag `housing`. A new structure, unit or advance is a JSON file plus its description in `text.js`; new
  behaviour that isn't a field yet belongs in `content.py` as a field, not as a special case by id.

## Map
- `server.py`: `SETTINGS`, `ORDERS` (message -> argument readers; every order is `Match.act`), turn timer.
- `logic/match.py`: `Match`: setup, state helpers (`add_structure`, `add_unit` / `move_unit`, `remove_unit`,
  `structures_of` / `units_of` / `has_hall`, `refresh`), `act` / `set_done`, `resolve`, `score`, `public`,
  `private`.
- `logic/orders.py`: one function per order; `site_problem` / `recruit_problem` / `found_problem` /
  `claim_problem` are shared with resolution and the private state.
  `auto_train` places each structure's auto-train recruit (`s["train"]`) at the start of planning.
- Swords (`HELD` in content.py) aren't stored or spent: `logistics.stock` gives what working structures make
  minus what living units and recruit orders hold (`logistics.held`), so any way a unit dies frees its swords
  with no bookkeeping. `take` / `give` only check them.
- `logic/economy.py`: staffing, jobs, output (with boosts), housing, `report` (income, upkeep, trades, food, waste, flows),
  `end_of_turn`. `logic/logistics.py`: goods in stores. `logic/construction.py`: sites built with hammers.
- `logic/territory.py`: free land around Town Halls (first come, first served) plus bought land
  (`m.claims`: upkeep, lost to adjacent enemies or when cut off).
- `logic/standing.py`, `logic/explore.py`: standing orders (Explore / Fight / Pillage / Travel).
- `logic/recruiting.py`, `logic/combat.py`, `logic/movement.py`, `logic/vision.py`, `logic/mapgen.py`,
  `logic/bots.py` (bot seats `b1`...; plan through `Match.act` like players).
- `client/text.js` (`HexText`): rules, hints, tooltips, descriptions. `client/map.js` (`HexMap`): SVG map,
  pan/zoom, overlays, resource view. `client/hud.js` (`HexHud`): top bar, panels, structure card, trade,
  build menu. `client/panels.js`: tech tree, turn report, log. `client/replay.js`: combat replay.
  `client/game.js`: UI state, input, render loop.
- `client/art/`: terrain PNGs (`terrain/<terrain>[_n].png`, 208 x 240, listed in map.js `TERRAIN_ART`) and
  unit PNGs (`units/<file>`, named by a unit's `art`). Blank templates are in each folder.

## Pitfalls
- Under fog, a refusal must not reveal hidden things: planning checks pass the player's view
  (`seen=`, `planning=True`); resolution re-checks the truth and reports a "failed" event.
- Tests place pieces by hand: `helpers.blank` turns fog off unless asked; call `m.refresh()` after placing.
- Only gold is in `players[pid]["res"]`: goods are in stores and faith/science are flat (working structures'
  output minus `players[pid]["spent"]`), so always use `logistics.stock` / `take` / `give`.
- Never use a `type` key in game messages (the lobby envelope owns it); build/recruit say `kind`.
- Unit ids sort as strings ("u10" < "u9"); use the `n` field (or dict order) for age.
- A new thing that takes cells must also be checked in `orders.site_problem`, the bots' free-cell checks and
  the client's `buildProblem`.
- `orders.clear_unit` ends a standing order; standing orders re-plan with `keep_auto=True`.
- A player can be knocked out mid-resolution: loop over `self.alive()` again after each stage.
- The client's placing preview (`game.js` `outputAt`) mirrors `economy.output`; keep the two in step.
- SVG shapes without a fill are black: overlay cells get `hr-hlcell` (fill: none) until highlighted.

## Ideas
- Ships carrying land units, capturing cities, diplomacy.

# Hex Realms: developer notes

Rules and the message list: the docstring at the top of `server.py`; resolution order and score
in `logic/match.py`'s header. Content: `structures/`, `units/`, `advances/` (one JSON per item,
fields in `logic/content.py`). Tests: `tests/` (`python3 -I tools/run_tests.py hex-realms`).

## Read this game to learn
- **Simultaneous secret orders resolved together.** Everyone plans at once; orders live in
  `Match.orders[pid]` (private state only) and are paid for when given (refunded on cancel or
  failure), so nobody can over-order. Public stock is a start-of-turn snapshot (`Match.shown`)
  so spending doesn't leak plans. `done` flags + "all alive players done" resolve the turn;
  any new order clears your `done`.
- **Simultaneous movement with collisions** (`logic/movement.py`): paths are fixed at order
  time; resolution moves every unit one cell per step, with swaps, shared targets, chains of
  followers and blocked units handled in a fixed order. Fighting stops both units, which keeps
  the rules short (no "winner moves in" special cases).
- **Dice combat** (`logic/combat.py`): d6 pools, 4+ to hit, 5+ against cover, up to 3 rounds;
  every roll is in the event so the client can show it. Tests use `tests/helpers.FixedDice`
  (every die shows one face) to make outcomes certain.
- **Multi-cell hex structures**: footprints are axial offsets; `gamekit.hexes.rotations`
  precomputes the 6 turns, sent in the content so the client draws ghosts.
- **Goods that travel** (`logic/logistics.py`): goods live in stores (per-structure `stock`);
  producers flagged `road` keep a one-turn `held` buffer and deliver along road networks (roads
  plus `navigable` structures; a network needs at least one road). Spending takes from Town
  Halls and stores on a Town Hall's network only; an unlinked store still fills. Gold, faith and
  science are realm-wide. Every structure works if staffed (`logic/economy.py`: jobs filled food
  first, then oldest).
- **Fog of war as per-viewer private state** (`logic/vision.py`): the public state has no map;
  each member's private state carries `view` (explored cells, dimmed cells, structures as last
  seen, units in sight, filtered events). Planning uses only what the player knows (unexplored
  cells cost 2, hidden enemies don't block); resolution uses the truth, with real movement
  points, so hidden things are discovered by running into them. The client merges `view` into
  `game` in `onState`, so the rest of the page reads `game.cells` / `game.units` as before.
- **A free first city**: everyone starts with Settlers; the starting goods wait in
  `players[pid]["startGoods"]` until the first Town Hall. Players are out only with no Town
  Hall *and* no Settlers; a realm without a hall skips eating and growth.
- **A turn timer**: `server.py` schedules a timeout per turn (checked against the turn number).

## Map
- `server.py`: `SETTINGS`, `ACTIONS` (one thin method per message → `Match.act`), turn timer
  (`start_timer` / `timeout` / `after_resolve`).
- `logic/match.py`: `Match`: setup (map, halls, militia), state helpers used by the other modules
  (`add_structure`, `remove_unit`, `move_unit`, `refresh` = territory cache), `act` / `set_done`,
  `resolve` (+ `_found`, `_builds`, `_recruits`, `_heal`, `_eliminate`, `_check_end`), `score`,
  `remove`, `public`, `private` (orders, economy forecast, unit reach, recruit reasons, valid
  founding rotations).
- `logic/orders.py`: one function per order; `site_problem` / `recruit_problem` /
  `found_problem` are shared with resolution (re-checked then) and the private state.
- `logic/vision.py`: `update` (after every change via `Match.refresh`), `known_at`, `view`.
- `logic/movement.py`, `logic/combat.py`, `logic/economy.py`, `logic/logistics.py`, `logic/mapgen.py`,
  `logic/content.py`: see their headers.
- `client/map.js`: `HexMap.create`: pan (drag) / zoom (wheel) SVG map; terrain layer rebuilt only
  when `game.cells` changes, the rest per state; roads in their own layer under the structures,
  one colour for everyone, and `roadLinks` draws one line per (connected road group, structure); `setHighlights` / `setGhost` / `flash` only
  touch overlays. `HexMap.util` has the client's hex maths (dist, neighbors, add).
- `client/hud.js`: `HexHud`: top bar (stock + net, people, End turn), players, selection panel
  (unit / structure actions, recruit buttons with the server's reasons), orders list, trade,
  build menu. `client/panels.js`: `HexPanels`: advances, last-turn report (dice faces), log.
- `client/game.js`: UI state (`ui.sel`, `ui.mode` build / shoot / found + rotation, tab), click
  and key handling, highlights and the build ghost (its green/red is only a hint; the server
  decides), the turn countdown (approximate: restarts on reload).
- `tests/`: `test_rules.py` (Match on a blank all-grass map: `helpers.blank`, `hall` (with the
  starting goods), `unit`, `rich`, `stock` = what a player can spend), `test_lobby.py` (Sim: secrecy, done, timer, leaving).

## Balance notes (reasoning, not simulation)
- Start: 3 people, housing 4, and the goods in the Town Hall (25 of each at most); the hall
  alone nets +1 food, so you grow once, then need a Hut (2 wood) or House. Every early producer
  also needs a road (1 wood per cell) to the hall, and the hall's 25-cap makes a Storage Yard or
  Granary on the network the next limit. Three starting people can staff only three of farm / lumbermill /
  mine, which is the opening choice.
- Sieges are slow on purpose: a Swordsman does ~2 damage a turn to a 15 hp Town Hall and takes
  ~1 back, so taking a city needs 3+ units or Catapults (3 damage per hit, from range, no reply,
  but towers shoot them).
- Score: population + units + 3 per advance + structure scores + gold // 10, so a peaceful
  builder can win on the turn limit; conquest ends it early.

## Pitfalls seen here
- Under fog, a validation error must not reveal hidden things: order checks pass the player's
  view (`site_problem(..., seen=)`, `found_problem(planning=True)`, `shoot` only at what you see),
  and resolution re-checks the truth (a failed order becomes a "failed" event for its owner).
- Rules tests place pieces by hand: `helpers.blank` turns fog off unless asked (`fog="on"`, then
  `m.refresh()` after placing).
- SVG shapes without a fill are black: the highlight overlay (one polygon per cell, above the
  terrain) once painted the whole map black. Overlays get the `hr-hlcell` class (fill: none)
  until highlighted.
- A stray double quote inside a double-quoted string in `client/hud.js` stopped the file
  loading: the map drew but every panel stayed empty. `tools/jscheck.py` now flags a string
  followed by a word on the same line.
- Goods aren't in `players[pid]["res"]` (that's gold/faith/science only): read them with
  `logistics.stock`, spend with `logistics.take` / `orders.pay`, refund with `give`.
- Never use a `type` key in game messages: the lobby envelope is `{"type": "game", ...}` and
  yours overwrites it (the message silently does nothing). Build/recruit say `kind`.
- Unit ids sort as strings in `movement.resolve` ("u10" < "u9"): deterministic, but not by age;
  use the `n` field when age matters (desertion, tower targets).
- A player can be knocked out mid-resolution; loops over players use `self.alive()` again after
  each stage, and `remove_unit` also clears that unit's orders.

## Not done yet (ideas)
- Fog of war, ships carrying land units, capturing (instead of destroying) cities, diplomacy.

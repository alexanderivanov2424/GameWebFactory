# Deep Colony: developer notes

Rules and the message list: the docstring at the top of `server.py`. Modules: `logic/__init__.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py deep-colony`; one file alone:
`cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_fluids.py`).

## Read this game to learn
- A `RealtimeGame` whose players never control a unit: shared orders, shared pause/speed
  (the tick runs `speed` steps, or none while paused), live cursors/drag boxes as realtime
  *input* (held state), exact hover info in `private_state` from that input.
- A big grid over `Snapshots`: grid layers sent as one string per row keyed by row index,
  rebuilt at most every half game second, so a delta only carries rows that changed.
- A cell simulation (one element per cell with mass/temperature/germs) in flat lists.

## Map
- `elements/*.json`, `buildings/*.json`: content (schema in `logic/content.py`'s docstring).
- `logic/match.py`: `Match.step(dt)` order: every `FLUID_DT` fluids → heat → germs → debris
  settles; decor when buildings/items change; then `networks.step`, `machines.step`,
  `chores.step`; dead colonists removed and logged; all dead → `result`.
- `logic/view.py`: the public/private state (the client contract). `server.py`: lobby glue.
- Colonists: `nav.py` (standable cells, BFS `distances`, `path`), `dupes.py` (needs, walking,
  falling), `chores.py` (choose/run loop, `cancel_for`) with the chores themselves split into
  `chore_common.py`, `chore_survival.py` (breathe, eat, toilet, wash), `chore_jobs.py` (operate,
  build, dig, deconstruct, harvest, empty) and `chore_haul.py` (supply, haul). Each chore is a
  generator with `try/finally`, so closing it releases reservations and drops a carried load.
- Machines: `networks.py` (wire/pipe components rebuilt on `buildings.version`, power split,
  pooled pipe buffers), `machines.py` (`KINDS` per building kind + the chore API).
- `client/`: `game.js` (lobby wiring, layout), `grid.js` (row decoding), `render.js` (canvas),
  `tools.js` (mouse/keys → orders and input), `panels.js` (DOM side panels).

## Contracts between modules
Coordinates: x right, y down; cell index `i = y * w + x`. Building x, y = top-left cell.
Game time in seconds; a cycle is `match.CYCLE` (600 s). Mass kg, temperature °C, heat kJ.

**World (`grid.py`)**: flat lists `el, mass, temp, germs, tile, door, ladder, insul, decor`;
`blocks_fluid(i)`, `is_gas/is_liquid/is_solid/is_vacuum(i)`, `set_cell`, `add_mass`,
`emit(x, y, el, kg, temp, germs)`, `take(i, ids, kg)`, `dig(i)`, `add_heat(i, kj)`, `nbrs[i]`.
`content.PHASE/SHC/COND/DENSITY[el index]` for hot loops.

**Rotation**: `b.rot` 0-3, `b.w`/`b.h` rotated size; always use `b.cells()`, `b.bottom_cells()`,
`b.port_cell(key)` (ports: powerPort, pipeIn, pipeOut, gasIn, gasOut), never `b.d["w"]`.
**Never lose mass**: `world.release(x, y, el, kg, temp, germs)` = emit, and whatever doesn't fit
waits in `world.pending` (retried by `world.drain_pending()` each fluid step). Machines don't
release blindly: when their output can't be placed they keep it in `b.state` and block
("Overpressure").
**Stores**: `b.deliver(el, kg, temp, germs)` (temperature averaged by mass in `b.store_temp`,
germs onto the structure `b.germs`), `b.take(el, kg) -> (kg, temp, germs)` (a share of the
structure's germs leaves with it). Never write `b.store[...]` directly outside buildings.py.
`b.filter` (None = all) / `b.accepts_element(el)` for storage kinds with `filterable`.
**Germs on things**: `germs.touch(match, dupe, b, dt)` exchanges germs between a colonist and a
structure they work at or use (call it from chores); structures' and debris germs die off.
**Sweep**: `item.sweep` ({"by", "prio"} or None); only swept debris is hauled to storage
(supply and eating still take any debris).
**Research** (`research.py`): `match.research.is_unlocked(btype)`, `select`, `add_points`;
Research Station behaviour is in research.py (machines delegates).
**Schedules** (`schedule.py`): `match.schedules.block_for(dupe)` -> "w"/"d"/"s"; `Dupe.schedule`
("1"-"3"), `Dupe.stamina` 0-100, `Dupe.asleep`; beds are buildings with `d["bed"]`.

**fluids / heat / germs / mapgen**: `fluids.step(world, dt)`, `heat.step(world, dt)`,
`germs.step(world, items, dt)`, `germs.update_decor(world, buildings, items)` (fills
`world.decor`), `mapgen.generate(w, h, rng) -> (World, (pod_x, pod_y))`.

**Dupe (`dupes.py`)** fields others read/write: `id` ("d1"), `name`, `x`, `y` (floats in cell
units; standing cell = `(round(x), round(y))`), `breath` 0-100, `kcal` 0-4000, `bladder`
0-100, `stress` 0-100, `health` 0-100, `germs` (float), `sick` (s left, 0 = healthy),
`needs_wash` (bool, set by toilets), `carry` (None or `{"el", "kg", "temp", "germs"}`),
`task` (short text), `dead`, `death` (cause text). `dupes.spawn(match, count, x, y) -> [Dupe]`.

**chores.py**: `step(match, dt)` (needs, choosing, moving, working for every colonist),
`cancel_for(match, target)` with target `("building", bid)`, `("dig", i)` or `("dupe", did)`:
drop chores aimed at it and release their reservations (`Item.reserved`, `Building.reserved`).

**Networks (`networks.py`)**: `Networks(match)`; `.step(dt)` rebuilds components when
`buildings.version` changed, then distributes power and sets `b.powered` on every power user;
`.pipe_take(b, port, ids, kg) -> (el, kg, temp, germs)` (`port` = "pipeIn"/"pipeOut", `ids`
None = any liquid), `.pipe_put(b, port, el, kg, temp, germs) -> kg accepted`,
`.pipe_has(b, port, el) -> kg`, `.pipe_room(b, port) -> kg`, `.needs_power(b) -> bool`
(the network at b's power port wants more: unpowered active users or batteries not full),
`.power_summary() -> {nid: {"gen", "use", "stored", "cap"}}`, `.pipe_summary() -> {nid: {el: kg}}`.
Machines mark `b.state["active"]` (wants power this step) and `b.state["producing"]` (generator on).

**machines.py** (used by chores): `step(match, dt)`; `wants_operator(match, b)`;
`operate(match, b, dupe, dt)` (called every step a colonist works at an operated building);
`toilet_usable(match, b)`, `use_toilet(match, b, dupe)` (bladder 0, adds germs, sets
`needs_wash`); `basin_usable(match, b)`, `wash(match, b, dupe)` (germs 0, `needs_wash` False);
`harvest_ready(b)`, `harvest(match, b)` (drops the crop as debris); `needs_emptying(b)`,
`empty(match, b)` (drops contents as debris); `storage_room(b, el) -> kg` (storage: anything;
ration box: food only).

**orders.py**: `match.digs`, `finish_dig/finish_build/finish_deconstruct`, `DIG_TIME`, `DECON_TIME`.

## Pitfalls seen here
- Two pipe ports of one building must not be 4-adjacent: pipes on touching cells join into one
  network, mixing input and output (lavatory/wash basin are 2x2 with diagonal ports).
- A pipe network holds 10 kg per segment, so a machine needing more per use than its pipe holds
  never starts (keep per-use amounts small or the pipe long).
- Power reacts a step late (`active`/`producing` are set by machines after the network step).
- Colonists build within 1 cell (Chebyshev) and dig up to 2 above: build ladders up from a floor.
- Terrain changes outside buildings/digs (fluids freezing, tiles finishing) aren't in the nav
  cache key, so the cache also refreshes once per game second; colonists caught inside solid
  are moved out (`dupes.unstick`), and ones that lose their footing fall and re-path.
- `networks.needs_power` must stay true while a generator feeds active users, or the operator
  quits, power drops and the two chores flip back and forth forever.
- Map starts are stamped (`mapgen._stamp_start`) so every size gets the basic resources nearby.
- Real-time: state changes reach clients with the next tick (tests: `sim.tick(1)` before reading).
- Never put None into the public state (Snapshots deletes the key); quantize floats.

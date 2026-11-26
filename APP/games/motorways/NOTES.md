# Metro Lanes: developer notes

Rules and the message list: the docstring at the top of `server.py`. Modules: `logic/__init__.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py motorways`).
A multiplayer take on Mini Motorways: one shared city, everyone with their own stock of pieces,
the same weekly rewards for all, points by road ownership, shared loss on overflow.

## Read this game to learn
- A `RealtimeGame` whose players never move a unit: they edit a shared graph (road tiles and
  links, owned per player) with one-off ACTIONS while the simulation (cars) runs on the tick.
  Real-time input is only the mouse cursor, shown to the others.
- Traffic on a tile graph (`logic/traffic.py`): per-direction lanes with a following gap,
  junction holds with capacities (plain / lights / roundabout), a give-up timer so gridlock never
  lasts, and lazy re-routing when the graph's `version` changes. Routes are Dijkstra trees towards a
  target, cached per graph version (`RoadNet.tree`).
- A shared pause for a simultaneous pick (`Match.offers`, the weekly upgrade) inside a real-time
  game, with a timeout that picks for whoever didn't.
- Client-side checks that mirror the server (`client/city.js`) so a mouse drag doesn't spam the
  server with steps it would refuse; the stroke stops at the first local failure.

## Map
- `logic/match.py`: `Match.step(dt)`: pick countdown (pauses everything else) -> `city.step`
  (spawns, pins, overflow timers) -> `traffic.step` -> loss -> new week (area grows, deliveries, offers).
- `logic/roads.py`: `RoadNet`: `draw` (roads, driveways, `_span` for bridges/tunnels),
  `place` (roundabout/light), `erase` (refunds, also to other owners), `edges`/`junction`/`tree`/`route`,
  `step_owner` (who scores a car's step: 1 per road tile), `owner_shares`.
- `logic/city.py`: houses/shops, spawn placement (houses in clusters: `grow_cluster`), demand, overflow. `logic/grid.py`: tiles, terrain
  generation, the area. `logic/players.py`: stock. `logic/upgrades.py`: offers. `logic/view.py`: client contract.
- `client/`: `game.js` wiring, `city.js` lookups + mirrored rules, `view.js` canvas (incl. the "+1" pops in the builder's colour, worked out client-side from car positions), `input.js` tools and
  strokes, `hud.js` boxes (top clock, players, tool bar, pick dialog, result).

## Pitfalls seen here
- Buildings are not road tiles: a house/shop node links to its door tile only while that tile has a
  road (`RoadNet.edges`). Drawing into a building is only allowed from its door, and just puts a road there.
- A car waiting at the end of its lane (d == length) must retry the lane change every tick before
  the "can't move" check, or it never leaves (`Traffic._drive` handles the node first).
- Points are credited live in `Traffic._drive` as a car leaves each tile (`_credit_step`), both ways;
  `Car.driven` (tiles actually passed to the shop, after re-routes) only decides whose `trips` count.
- Spans (bridges/tunnels) are road tiles with kind "b"/"t" that only link along the span; both the
  server and `city.js` refuse other links to them.

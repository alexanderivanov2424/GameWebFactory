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
- **Goods in stores** (`logic/logistics.py`): goods live in stores (per-structure `stock`), all
  usable wherever they are. Production and upkeep happen at the same time (2026-11-15, the user's call:
  upkeep comes out of the stores, then out of this turn's production, `economy.split_upkeep`); only what
  is left at the end of the turn fills the stores (Town Halls first) and the rest is lost. Gold,
  faith and science are realm-wide. Every structure works if staffed (`logic/economy.py`: jobs
  filled food first, then oldest).
- **Honest forecasts** (`economy.report`): `net` is income - upkeep, not capped by the stores (the
  user's call: 21 of 25 food, +7, -3 shows +4, not +1), and `wasted` is what won't fit at the end
  of the turn, `growth` is the people you will really gain (0 with a
  reason in `growthWhy`), and `idle` excludes builders. Growth needs more food made than eaten,
  not food that fits in the stores. `flows` breaks the same numbers down per structure / unit / site
  (`economy.flows`: production +, unit upkeep -, the people's food on the first Town Hall, and for
  "people" jobs / builders - and housing +) for the client's **resource view** (click a top-bar chip:
  `map.setResView` greyscales the `hr-base` group and draws outlines and +n / -n badges above it).
- **No roads; land is bought** (2026-11-11, the user's call): roads (first carrying goods, then laid
  automatically) were removed. Structures go anywhere in your territory, with no "must touch"
  rule. `orders.claim` is an order paid in gold (`CLAIM_COST`); at resolution (`Match._claims`,
  before builds) the cell and its free neighbours become weak land (`m.claims`).
- **Strong and weak land** (`logic/territory.py`, 2026-11-14, the user's rules): structures' reach is
  strong land, first come, first served (`m.territory` is kept between refreshes; a cell stays its
  owner's while they still reach it, a free cell goes to the only player reaching it, nobody while
  two or more do). Bought land is weak, per cell in `m.claims`, and lost for good when an enemy
  unit stands on or next to it (`territory.unit_entered`, called by `Match.add_unit` / `move_unit`, so
  passing through counts mid-move), when any structure of another player reaches it, or when it's
  no longer connected to its owner's strong land (both in `territory.territory`, run by `refresh`);
  your own structure reaching it makes it strong (it leaves `m.claims`). Claims need no enemy unit
  on or next to the target (`claim_problem` checks what you see, `_claims` the truth). The client
  gets `claims` in the view and draws weak land with a dashed border (territory is never shaded inside).
- **Standing orders** (`logic/standing.py`, 2026-11-11 feedback): `u["auto"]` (explore / fight /
  pillage / travel, plus `u["goal"]` for travel) survives the per-turn order reset; `standing.plan_all`
  gives each such unit this turn's ordinary order (move / shoot / hold) as planning starts, and any
  other order for the unit (`orders.clear_unit`) ends it. Fight and Pillage pick targets the owner
  sees and never end on their own (they hold when there's nothing); Pillage fights enemy units within
  `ALERT` first. A move to a cell out of reach is a Travel order: `movement.route` (no budget, any
  number of turns) cut to this turn by `movement.this_turn`. Explore's cell choice is
  `explore.target` (bots scout with it too). Units with an order this turn or a standing order are
  listed in `private.ordered` and greyed out on the map; the client deselects a unit once commanded.
- **Own units pass through each other** (`movement.pass_friends` and the swap in step 5): a unit
  blocked by its own side hops over it (and any friends behind) to the next free cell of its path,
  paying for every cell crossed; two of your units moving into each other's cells swap. A path that
  ends on a friend still stops.
- **Fog of war as per-viewer private state** (`logic/vision.py`): the public state has no map;
  each member's private state carries `view` (explored cells, dimmed cells, structures as last
  seen, units in sight, filtered events). Planning uses only what the player knows (unexplored
  cells cost 2, hidden enemies don't block); resolution uses the truth, with real movement
  points, so hidden things are discovered by running into them. The client merges `view` into
  `game` in `onState`, so the rest of the page reads `game.cells` / `game.units` as before.
- **A free first city**: everyone starts with Settlers; the starting goods wait in
  `players[pid]["startGoods"]` until the first Town Hall. Players are out only with no Town
  Hall *and* no Settlers; a realm without a hall skips eating and growth.
- **Construction by idle people** (`logic/construction.py`): a resolved build order becomes a site
  (`m.sites`, cells in `m.cell_site`), kept apart from `m.structures` so nothing else has to skip
  unfinished buildings. Each turn of work (`buildTurns`) needs `builders` people without a job,
  counted before production and spent after it, oldest site first; jobs are filled first, so
  players free builders with Switch off / Jobs off (`staff`) / Demolish. Sites show in `view.sites`
  (own always, others' only while seen; not remembered under fog). An enemy unit on any cell of a
  site stops its work (`construction.blocked`); building where a seen enemy unit stands is refused.
- **A turn timer**: `server.py` schedules a timeout per turn (checked against the turn number).
- **Bots in the seats** (the user asked for them): the `bots` setting adds seats `b1`... to the
  `Match` (not lobby members). `logic/bots.py` plans each bot's turn as the turn starts
  (`Match.plan_bots`, after setup and after each resolve) through `Match.act`, so they obey the
  same checks and fog, and marks them done. The game ends once no person is left.

## Map
- `server.py`: `SETTINGS`, `ACTIONS` (one thin method per message → `Match.act`), turn timer
  (`start_timer` / `timeout` / `after_resolve`).
- `logic/match.py`: `Match`: setup (map, halls, militia), state helpers used by the other modules
  (`add_structure`, `add_unit` / `move_unit` (both unclaim weak land an enemy unit touches), `remove_unit`, `refresh` = territory cache), `act` / `set_done`,
  `resolve` (+ `_found`, `_builds`, `_heal`, `_eliminate`, `_check_end`), `score`,
  `remove`, `public`, `private` (orders, economy forecast, unit reach, recruit reasons, valid
  founding rotations).
- `logic/orders.py`: one function per order; `site_problem` / `recruit_problem` /
  `found_problem` are shared with resolution (re-checked then) and the private state.
- `logic/construction.py`: `start` / `progress` (resolution), `plan` / `forecast` (who builds what this
  turn: `private.building`), `remove` (demolish).
- `logic/standing.py`: `start` / `plan` / `plan_all` / `stop`, one helper per mode (`travel`, `attack`).
- `logic/explore.py`: `target` (where an exploring unit goes).
- `logic/bots.py`: `plan(m, pid)`: the bot strategy (header lists it; constants at the top).
- `logic/vision.py`: `update` (after every change via `Match.refresh`), `known_at`, `view`.
- `logic/recruiting.py`: `spawn_cell` (on the structure first), `resolve` (recruit orders appear, take the
  structure's `autoOrder` as `u["auto"]`), `set_auto` (the `autorecruit` message) and `plan` (each turn's
  automatic recruit orders, marked `"auto": True`, only with people who have no job).
- `logic/territory.py`: `territory` (strong + weak land, returns both maps), `unit_entered`, `claim_cells`, `threatened`.
- `logic/movement.py`, `logic/combat.py`, `logic/economy.py`, `logic/logistics.py`, `logic/mapgen.py`,
  `logic/content.py`: see their headers.
- `client/art/`: PNG art at 4x map size (sharp at the 3x max zoom). `terrain/<terrain>[_n].png` (e.g. plains.png, mountain_1.png) (208 x 240, one
  pointy-top hex 207.85 wide; corners (103.9,0) (207.8,60) (207.8,180) (103.9,240) (0,180) (0,60)) is drawn over the
  flat colour for the terrains listed in map.js's `TERRAIN_ART` (variants with weights, picked per cell by a hash of
  the cell key, so every viewer sees the same map; add a new file there). Cells are drawn top row first, left
  to right, so a tile's art can spill up over the tiles above it (only inside its own 208 x 240 box). `terrain/terrain_template.png` (hex outline)
  and `units/unit_template.png` (the unit disc, radius SIZE * 0.42 = 12.6 on the map: 100 x 100) are blank
  templates. Units with an `art` file (units/*.json, a name in `units/`) draw it over their owner-coloured disc
  instead of the icon (map only; panels keep the emoji); units without one and structures still draw emoji.
- `client/map.js`: `HexMap.create`: pan (drag) / zoom (wheel) SVG map; terrain layer rebuilt only
  when `game.cells` changes, the rest per state;
  structures are solid in their content `color`, drawn by `blob` (cells at 80% with the gaps
  between a structure's own cells filled, so only its outside is inset); owner colours show on the
  territory border (drawn just inside the cells, its outer edge on the cell edge (`BORDER`, `BORDER_W`, `outline`), so two realms' borders sit side by side; opaque lines in one group with the opacity, so overlaps don't darken) and as an outline on hover (`hoverG`, `shapeAt`), and the icon (emoji from the content, placeholder for art) at their middle; `setHighlights` / `setGhost` / `flash` only
  touch overlays (a selection, "sel" cells, is outlined round its outside only, in `selG`). `HexMap.util` has the client's hex maths (dist, neighbors, add).
- `client/hud.js`: `HexHud`: top bar (stock + net, people: jobs / building / idle, growth only when
  it will happen, Jobs off / on, End turn), players, selection panel (unit / structure / site actions, Explore, recruit buttons with the server's reasons, automatic
  recruiting selects), orders list, trade, build menu. `client/panels.js`: `HexPanels`: `techTree` (advances of one
  currency laid out by prerequisite depth, absolutely placed nodes over an SVG of links), last-turn report (dice faces), log.
  The tech tree opens in the `#tech` popup (`ui.tech` = the open currency tab), which covers row 2 of the `#hud` grid,
  so `#col-left` / `#col-right` are placed explicitly (an auto-placed column would be pushed below it).
- `client/replay.js`: `HexReplay`: the end-of-turn combat replay (glides with `map.focus`, dice per round
  left = you / right = them, `map.mark` rings, back to the saved view). `steps(game, you)` turns battle /
  shot / siege / tower events into steps; each unit side carries `need` (the roll that hits it, from
  `combat.side`). Player settings (speed, skip) via `AppSettings.addPageSettings`. game.js starts it where
  it used to only flash the cells (a new `game.step`); Esc or the Skip button stops it.
- `client/game.js`: UI state (`ui.sel`, `ui.mode` build / shoot / found + rotation, tab, `ui.tech`, `ui.resView`), click
  and key handling (`selectAt` cycles unit -> structure -> site on repeated clicks), highlights and the build ghost (its green/red is only a hint; the server
  decides), the turn countdown (approximate: restarts on reload).
- `tests/`: `test_rules.py` (Match on a blank all-plains map: `helpers.blank`, `hall` (with the
  starting goods), `unit`, `rich`, `stock` = what a player can spend), `test_lobby.py` (Sim: secrecy, done, timer, leaving).

## Balance notes
- Map radius = 9 + 3 per realm (bots count) + map size (small -3, large +4, huge +8), 2 less solo.
- Bot-only test games (scratch, 80 turns, before build times and the weaker Town Hall): bots reach 2-3 cities, ~12 units, fight and siege from
  turn ~20 but rarely take a city; a turn with 5 bots takes under 0.2 s.
- Start: 3 people, housing 4, and the goods in the Town Hall (25 of each at most); the hall makes
  only 1 gold and 2 food (no wood, stone, science or faith: the early game is slow on purpose), so
  you grow once, then need a Hut (2 wood) or House. Building takes turns and idle people (Farm 2
  turns x 1 builder, House 2 x 2, University 4 x 3, Monument 5 x 3), and every worker in a job is
  one builder fewer, so the opening is a choice between producing and building. The hall's 25-cap
  makes a Storage Yard or Granary the next limit. Territory grows with structures (radius 2, the hall
  3) or gold per claimed cell (2), so gold also buys room to expand.
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
- A new kind of thing on the map that takes cells must also be checked in `orders.site_problem`
  (sites are: `m.cell_site`), the bots' `taken` / `free_cells`, and the client's `buildOk`.
- Standing orders re-plan through `orders.clear_unit(..., keep_auto=True)`; a plain `clear_unit` ends the
  standing order, so call it only for a new order from the player.
- A player can be knocked out mid-resolution; loops over players use `self.alive()` again after
  each stage, and `remove_unit` also clears that unit's orders.

## Not done yet (ideas)
- Ships carrying land units, capturing (instead of destroying) cities, diplomacy.

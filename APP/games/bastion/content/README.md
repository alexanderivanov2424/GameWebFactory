# Bastion content files

One JSON file per item; the file name (lowercase letters, digits, `-`, `_`) is its id. Bad files
are logged and skipped (logger "bastion"). Loaders: `logic/structures.py`, `logic/cards.py`,
`logic/enemies.py`, `logic/maps.py`. Resources: `gold`, `wood`, `stone`, `ore`, `wheat`, `bread`,
`tools` (gold is never stored in buildings; the others are "goods"; wheat and bread are food:
`logic/food.py`).

## structures/<id>.json
Buildings, plus the `road` and `wall` tiles and the `keep` (start only). Structures have no owner.
- `name`, `icon` (an emoji), `text` (shown in the inspector and on the blueprint)
- `shape`: rows of `#` (filled) and `.` (empty), at most 4x4; players may turn it, never mirror it
- `tile`: `"road"` or `"wall"` for tiles (cell sets, never worked; shape `["#"]`); leave out for
  buildings. Tiles have no blueprint card: players place them one at a time from the team's
  stock, and `cost` buys a batch of `BATCH` (3) when the stock is empty (`logic/tiles.py`);
  removing one is free. `price` and `bundle` are ignored on them
- `cost`: `{resource: n}` paid from the stockpile when built
- `price`: gold for its blueprint (`plan-<id>`) in the market; leave out to never sell it
- `bundle`: copies of the blueprint one purchase adds (1-5, default 1)
- `requires`: `[{"near": X, "min": n}]` all must hold where it's placed
- `work`: `{"uses": {resource: n}, "makes": {output: n}}`, one output: a resource, `soldiers`,
  `keep` (heals it) or `cure` (cures that many plagued buildings). A unit placed on it works it
  once a round; spending a tool adds `TOOL_BOOST` (1) output (`logic/economy.py`)
- `bonuses` (buildings that work): `[{"near": X, "min": n, "bonus": b}]` adds b when at least n
  are next to it, or `[{"near": X, "each": b, "max": m}]` adds b per one next to it (up to m).
  Negative values are penalties.
- `near` (X) is a terrain (`forest`, `mountain`, `water`, `grass`), `empty` (empty grass),
  `road` / `wall` (tiles), or a structure id (counts distinct buildings of that kind)
- `population`: people living there (0-10; houses, the keep). Ruined structures still count.
  Fed people become units each round (`logic/units.py`)
- `carriage`: `true` for a coach house: each undamaged one makes one haul a round carry `BIG`
  (5) goods instead of `SMALL` (3) (`logic/hauling.py`)
- `income`: `{resource: n}` made every round without a unit (the keep's gold)
- `depot`: buildings next to it deliver goods at once; haulers bring goods to it
- `protects`: radius (square) in which building tiles (and their stores) are safe from raids
- `card`: the card id added to the builder's discard pile when built (chapel: `absolution`)

## cards/<id>.json
Actions and enemy curses (blueprints are made from the structure files). Cards never work
buildings, haul or fight: units do that.
- `name`, `kind`: `"action"` (default) or `"curse"`, `price` (gold in the market; leave out to
  never sell it), `text` (optional: generated from the fields otherwise)
- Actions, any of: `cost` `{resource: n}` paid when played; one target: `repair: true` (1 wood per
  ruined tile) or `cure: true`; plus `gain` `{resource or "soldiers": n}`, `draw` n, `trash` n
  (remove up to n other cards in the hand from the deck; not curses), `adds` card id (put in the
  player's discard pile when played: Tax adds Unrest)
- Curses: `pay` `{resource: n}` to play it (it then leaves the deck), `hurts: true` deals 1
  damage to the enemy that sent it (if that enemy has `defeat.cards`)

## enemies/<id>.json
- `name`, `icon`, `text` (flavour), `tier` 1-3 (a game's lineup: lower tiers first, a random
  tier-3 boss last), `hp` (1-50; scaled by difficulty and x the number of players: `logic/foes.py`)
- `defeat` (at least one): `soldiers` n per damage (soldiers from the counter, or units placed on
  Fighting it: each unit is 1 strike, strikes carry over), `resources` `{resource: n}` per damage,
  `cure: true` (each building it plagued that is cured hurts it), `cards: true` (each of its
  curse cards paid off hurts it), `raze` n soldiers or unit strikes per lair tile (needs `lair`;
  scaled like hp)
- `lair`: `{"name", "icon", "shape"}` placed on empty grass when it arrives; its tiles are its health
- `attacks`: 1-4 attacks made in turn, one per round. Each: `name`, optional `text`, and any of
  `steal` `{resource | "most": n}`, `loot` n (goods waiting in the stores of buildings with a tile
  that isn't next to a wall or within a watchtower's reach), `ruin` n (+ `prefer` [structure ids]),
  `keep` n (+ `shield`: each wall tile next to the keep blocks 1), `place` `{"name", "icon"}` +
  `count` (blight tiles: -1 output to buildings next to them; 1 soldier or unit razes one),
  `curse` card id + `to` `"each"` | `"one"`, `plague` n (no unit on them until cured), `freeze` n
  (no unit on them next round), `kill` n soldiers. Nothing: it rests.

## maps/<id>.json
- `name`, `rows`: equal-length strings (6-40 of them, 6-40 long; the shipped maps are 32 x 22) of
  `.` grass, `F` forest, `M` mountain, `~` water
- `start`: `[{"structure", "x", "y", "rotation"}]` the starting town (needs a `keep`); x, y is the
  top-left of the turned shape. Entries that don't fit are logged and skipped.

## starting-deck.json
`{card id: copies}` every player starts with. The round-1 hand always holds a `plan-house` when
the deck has one (`FIRST_CARD` in `logic/match.py`).

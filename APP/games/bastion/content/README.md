# Bastion content files

One JSON file per item; the file name (lowercase letters, digits, `-`, `_`) is its id. Bad files
are logged and skipped (logger "bastion"). Loaders: `logic/structures.py`, `logic/cards.py`,
`logic/enemies.py`, `logic/maps.py`. Resources: `gold`, `wood`, `stone`, `ore`, `food`, `tools`
(gold is never stored in buildings; the others are "goods").

## structures/<id>.json
Buildings, plus the `road` and `wall` tiles and the `keep` (start only).
- `name`, `icon` (an emoji), `text` (shown in the inspector and on the blueprint)
- `shape`: rows of `#` (filled) and `.` (empty), at most 4x4; players may turn it, never mirror it
- `tile`: `"road"` or `"wall"` for tiles (cell sets, never worked); leave out for buildings
- `cost`: `{resource: n}` paid from the stockpile when built
- `price`: gold for its blueprint (`plan-<id>`) in the market; leave out to never sell it
- `reusable`: `true` keeps the blueprint in the deck after building (roads, walls)
- `requires`: `[{"near": X, "min": n}]` all must hold where it's placed
- `work`: `{"uses": {resource: n}, "makes": {output: n}}`, one output: a resource, `soldiers`,
  `keep` (heals it) or `cure` (cures that many plagued buildings)
- `bonuses` (buildings that work): `[{"near": X, "min": n, "bonus": b}]` adds b when at least n
  are next to it, or `[{"near": X, "each": b, "max": m}]` adds b per one next to it (up to m).
  Negative values are penalties.
- `near` (X) is a terrain (`forest`, `mountain`, `water`, `grass`), `empty` (empty grass),
  `road` / `wall` (tiles), or a structure id (counts distinct buildings of that kind)
- `income`: `{resource: n}` made every round without a card (the keep's gold)
- `depot`: buildings next to it deliver goods at once; roads haul to it
- `protects`: radius (square) in which building tiles (and goods left on roads) are safe from raids
- `population`: people living there (cottages: 1); every Haul moves 1 more good per person
- `card`: the card id added to the builder's deck when built (chapel: `absolution`). Buildings with `work` get their
  crew card `crew-<id>` ("Work a <name>") unless `card` names another; `crew` names it.

## cards/<id>.json
Actions and enemy curses (blueprints and crew cards are made from the structure files).
- `name`, `kind`: `"action"` (default) or `"curse"`, `price` (gold in the market; leave out to
  never sell it), `text` (optional: generated from the fields otherwise)
- Actions, any of: `cost` `{resource: n}` paid when played; one target: `work` (`"any"` or a
  list of structure ids) with optional `boost` and `unskilled: true` (base output and penalties,
  no bonuses: Villagers), or `repair: true` (1 wood per ruined tile), or `cure: true`; plus
  `haul` n goods (+1 per population) with `reach` (cells each good moves along roads, default 4;
  goods that don't reach a depot are left on the road), `gain` `{resource or "soldiers": n}`,
  `draw` n, `trash` n (remove up to n other cards in the hand from the deck; not curses),
  `adds` card id (put in the player's discard pile when played: Tax adds Unrest)
- Curses: `pay` `{resource: n}` to play it (it then leaves the deck), `hurts: true` deals 1
  damage to the enemy that sent it (if that enemy has `defeat.cards`)

## enemies/<id>.json
- `name`, `icon`, `text` (flavour), `tier` 1-3 (a game's lineup: lower tiers first, a random
  tier-3 boss last), `hp` (scaled by difficulty and +50% per player after the first)
- `defeat` (at least one): `soldiers` n per damage, `resources` `{resource: n}` per damage,
  `cure: true` (each building it plagued that is cured hurts it), `cards: true` (each of its
  curse cards paid off hurts it), `raze` n soldiers per lair tile (needs `lair`)
- `lair`: `{"name", "icon", "shape"}` placed on empty grass when it arrives; its tiles are its health
- `attacks`: 1-4 attacks made in turn, one per round. Each: `name`, optional `text`, and any of
  `steal` `{resource | "most": n}`, `loot` n (goods left on road tiles that aren't next to a wall
  or within a watchtower's reach), `ruin` n (+ `prefer` [structure ids]), `keep` n (+ `shield`:
  each wall tile next to the keep blocks 1), `place` `{"name", "icon"}` + `count` (blight tiles:
  -1 output to buildings next to them), `curse` card id + `to` `"each"` | `"one"`, `plague` n,
  `freeze` n, `kill` n soldiers. Nothing: it rests.

## maps/<id>.json
- `name`, `rows`: equal-length strings (6-24) of `.` grass, `F` forest, `M` mountain, `~` water
- `start`: `[{"structure", "x", "y", "rotation"}]` the starting town (needs a `keep`); x, y is the
  top-left of the turned shape. Entries that don't fit are logged and skipped.

## starting-deck.json
`{card id: copies}` every player starts with.

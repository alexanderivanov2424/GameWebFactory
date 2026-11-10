# Bastion content files

One JSON file per item; the file name (lowercase letters, digits, `-`, `_`) is its id. Bad files
are logged and skipped (logger "bastion"). Loaders: `logic/structures.py`, `logic/cards.py`,
`logic/maps.py` (and the dormant `logic/enemies.py`). Resources (each player's own): `gold`,
`wood`, `stone`, `metal`, `food`, `tools`. Costs may also name `decrees` (royal decrees, each
player's allowance per planning phase).

## structures/<id>.json
Buildings (one tile each, owned by the player who placed them) and the `road` tile.
- `name`, `icon` (an emoji), `text` (shown in the details panel and on the blueprint)
- `tile`: `"road"` for road tiles (built by units on empty grass at resolution; no blueprint)
- `price`: gold for its blueprint (`plan-<id>`) in the market's blueprint half; leave out to never
  sell it (the `keep` is only placed at setup)
- `cost`: `{resource or "decrees": n}` paid when the blueprint is played
- `build`: build tokens it is planned with (0-5, default 1); each unit placed on it removes one;
  at 0 it is built and goes into effect
- `requires`: `[{"near": X, "min": n}]` all must hold where it's planned; X is a terrain (`forest`,
  `mountain`, `water`, `grass`), `empty` (empty grass), `road`, or a structure id
- `work` (what a unit stationed there does every round):
  - `{"makes": {resource: n}}`: automatic (farm, lumber mill, quarry)
  - `{"uses": {...}, "makes": {...}}`: the owner is asked each round ("Spend X to make Y?")
  - `{"choices": [{"makes": ...}, {"uses": ..., "makes": ...}]}`: the owner picks one (or none)
- `trains`: `true`: a worker placed here becomes a soldier (barracks)
- `staff`: who may be placed on it: `"worker"` (default), `"soldier"` (tower) or `"none"` (keep)
- `units`: workers it adds to its owner when built (house 2, keep 1)
- `income`: `{resource: n}` its owner gets at the end of every round (keep: 1 food, 1 gold)
- `decrees`: royal decrees it grants its owner each planning phase (keep: 3)

## cards/<id>.json
Actions and curses (blueprints are made from the structure files). Market cards are the ones with
a `price`: blueprints in one half, actions in the other.
- `name`, `kind`: `"action"` (default) or `"curse"`, `price` (gold; leave out to never sell it),
  `text` (optional: generated from the fields otherwise)
- Actions: `cost` `{resource or "decrees": n}` paid when played (every card costs 1 decree for
  now), plus any of: `gain` `{resource: n}`, `draw` n, `adds` card id (into the player's discard
  pile: Tax adds Unrest), `recall: true` (Orders: one of your stationed units back to your pool;
  targets a building), `trade: true` (give another player 3 different resources or 2 of one)
- Curses: `pay` `{resource or "decrees": n}` to play it (it then leaves the deck); `hurts: true`
  (dormant enemies) deals 1 damage to the enemy that sent it

## maps/<id>.json
- `name`, `rows`: equal-length strings (6-40 of them, 6-40 long; the shipped maps are 32 x 22) of
  `.` grass, `F` forest, `M` mountain, `~` water. Players place their own keep, house and farm.

## starting-deck.json
`{card id: copies}` every player starts with (Tax, 2 Orders, Trade).

## enemies/<id>.json (dormant)
Enemies are switched off; these files still load (`logic/enemies.py`) for when they come back.
Fields: `name`, `icon`, `text`, `tier` 1-3, `hp`, `defeat` (`soldiers`, `resources`, `cure`,
`cards`, `raze`), `lair`, `attacks` (`steal`, `loot`, `ruin` + `prefer`, `keep` + `shield`,
`place` + `count`, `curse` + `to`, `plague`, `freeze`, `kill`). See `logic/enemies.py`.

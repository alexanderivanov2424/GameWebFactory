# Bastion content files

One JSON file per item; the file name (without `.json`) is its id (lowercase letters, digits,
`-`, `_`). Files are loaded when the game is imported; a bad file is logged (logger "bastion")
and skipped, so check the server log after editing. Balance numbers live here, not in code.

## cards/*.json (logic/cards.py)
```json
{"name": "Archer Tower", "icon": "🏹", "kind": "tower", "labor": 2, "cost": 3, "unlock": 1,
 "shot": "arrow", "maxLevel": 3, "text": "Shown on the card.",
 "stats": {"damage": [3, 4, 6], "range": [2.5, 2.5, 3], "cooldown": 4, "air": true}}
```
- `kind`: `order` or a structure kind (below). `labor`: labor to play it (0-5). `cost`: market
  price in gold (0 = never offered). `unlock`: the first market that may offer it (the one after
  level N). `maxLevel`: 1-3 (default 3 for structures, 1 for orders). `shot` (towers): `arrow`,
  `bolt`, `rock`, `oil` or `none` (what the client draws).
- `stats`: each value is a number, `true`/`false`, or a list with one number per level. Only the
  stats listed for the kind are accepted:

| kind | goes on | stats |
|---|---|---|
| `tower` | grass | `damage`, `range` (cells, from the tower's center), `cooldown` (ticks between shots), `air` (hits flyers), `ground` (default true), `pierce` (ignores armor), `splash` (radius around the target, ground only), `minRange`, `area` (hits everything in range) |
| `wall` | road | `hp` |
| `spikes` | road | `damage` per tick to ground enemies on it (ignores armor) |
| `tar` | road | `slow` (% speed lost on it) |
| `barracks` | grass next to the road | `hp`, `damage`, `cooldown`, `respawn` (ticks; halved next to a farm) |
| `farm` | grass | `gold` per build turn for its owner |
| `forge` | grass | `bonus` damage for towers/barracks next to it |
| `watch` | grass | `bonus` range for towers next to it |
| `quarry` | grass | `labor` per build turn for its owner |
| `chapel` | grass | after each siege held: `keep` health, `repair` for walls next to it |
| `order` | — | `labor`, `draw`, `gold`, `keep`, `repair` (all walls), `teamLabor`, `teamGold`, `teamDraw` (everyone else), `upgrade` (true: pick a structure, +1 level) |

A new structure kind or order effect needs code (`logic/cards.py` KINDS / ORDER_STATS, then
`logic/battle.py`, `logic/match.py` or `logic/orders.py`, and `statLines` in `client/game.js`).

## starting-deck.json
`{"cards": {"archer-tower": 3, ...}}`: every player's deck at the start.

## enemies/*.json (logic/enemies.py)
```json
{"name": "Goblin", "icon": "👺", "hp": 26, "speed": 0.25, "keep": 1, "attack": 2, "attackEvery": 2,
 "text": "Quick and weak."}
```
`hp` is for 2 players on Normal (scaled by `PLAYER_SCALE` and `DIFFICULTY` in `logic/match.py`).
`speed`: road cells per tick (the client plays 8 ticks a second). Optional: `armor`, `keep`
(damage to the keep, default 1), `attack` + `attackEvery` (against walls and soldiers), `siege`
(multiplier against walls), `flying`, `regen` (hp per tick), `explode` (damage to the first
blocker, then it dies), `boss` (drawn bigger), `heal` `{"amount", "radius", "every"}`,
`summon` `{"enemy", "every", "max"}`, `breath` `{"radius", "every", "stun", "damage"}` (stuns
towers, hurts walls and soldiers in range).

## levels/*.json (logic/enemies.py)
Played in file-name order (`01-...`, `02-...`).
```json
{"name": "Goblin Scouts", "text": "Shown before the level.", "buildTurns": 3, "reward": 6,
 "waves": [{"enemy": "goblin", "count": 10, "road": "main", "start": 0, "gap": 8}]}
```
`buildTurns`: build turns before the siege. `reward`: gold for every player when it's held.
Each wave sends `count` enemies down `road` (`main` or `flank`), the first at tick `start`, then
one every `gap` ticks.

## maps/*.json (logic/maps.py)
```json
{"name": "Green Valley", "terrain": ["................", "..."], "keep": [0, 5],
 "roads": {"main": [[15, 2], [11, 2], [0, 2]], "flank": [[9, 9], [9, 2], [0, 2]]}}
```
`terrain`: one string per row (`.` grass, `^` rocks, `~` water, `T` forest; up to 24x24). Roads are
waypoints joined by straight runs, must end on the keep, may merge, and never cross themselves.
Road over water is drawn as a bridge. Every map needs both roads. A new map file shows up in the
host's Map setting automatically.

# Marooned content files

One JSON object per file; the file name (lowercase letters, digits, `-`, `_`) is the id.
Bad files are logged and skipped at import (`logic/content.py`, `logic/objectives.py`).
Adding a file needs no code unless it uses a new objective `check`.

## tiles/
| Field | Meaning |
|---|---|
| `name`, `icon`, `color`, `text` | How it looks (icon: an emoji; color: CSS). |
| `moveCost` | Energy to step onto it (1-5, default 1). |
| `resources` | `{item: count}` gatherable here; `-1` = never runs out. Items: wood, fiber, food, water, stone, scrap, herbs. |
| `searches` | Times it can be searched (draws a find). |
| `shelter` | People who sleep sheltered here (a cave: 1). |
| `reveals` | `true`: placing it also explores its unexplored neighbours. |
| `points` | Points for the first explorer (default 1). |
| `count` | `{"small": n, "large": n}` copies in the tile deck for a 7x7 / 9x9 island (topped up at random if short). |

## finds/
`name`, `text`, `gives` (`{item: count}`; items also include `relic`), `energy` (change, e.g. -1 for a snake), `count` (copies in the find deck).

## checks/
Build-check cards: `name`, `text`, `outcome` (`solid`, `shaky` or `snapped`), `count`. The deck's make-up is shown to players.

## objectives/
`title`, `text`, `points`, `role` (`castaway` or `imposter`: whose pool it's dealt from), `check` (a key of `CHECKS` in `logic/objectives.py`) and `param` (the number the check uses).

# Smugglers content files

Everything here is loaded at import by `logic/board.py` and `logic/content.py` (with
`gamekit.data`): a file that fails validation is logged and skipped, the rest still load.
The file name (without `.json`) is the id: 1-40 lowercase letters, digits, `-` or `_`.
The client draws everything from the state, so new content needs no client code.

## boards/<id>.json
```json
{
  "name": "Outer Rim", "width": 1020, "height": 660,
  "planets": {"kessar": {"name": "Kessar", "color": "#e53935", "x": 90, "y": 90}, ...},
  "routes": {"r1": {"from": "kessar", "to": "lumen", "length": 3}, ...},
  "starts": ["kessar", "drask"],
  "interpolHome": "tarsis"
}
```
- Planets: a name and art. The art is just a `color` for now (`#rrggbb`); every planet needs
  its own color so players can find it on the board and on contract cards. `x`/`y` are board
  coordinates (0..width, 0..height).
- Routes: `length` steps (1-9; the first board uses 2-5). A route of length L has L-1 dots,
  named `<route>.<n>` counted from `from`; ships can stop on them. An end may be a dot of
  another route **whose ends are both planets** (`"from": "r10.2"`), to branch off mid-route.
  Dots sit evenly on the straight line between the ends, so lay routes out so they don't
  cross planets.
- Every planet and dot must be reachable. `starts`: planets where smugglers' ships begin (each
  ship picks one at random). `interpolHome`: where new patrol ships start.
- Contracts aren't listed: they're generated from the board (`make_contracts` in
  `logic/content.py`: planets at least 4 steps apart, bonus = 1 per 3 steps).
- Today the game always uses `DEFAULT_BOARD` (`logic/match.py`). With several boards, add a
  host setting that picks one and pass it to `Match(..., board=...)`.

## goods/<id>.json
`{"name", "legal": true|false, "value", "count", "color", "text"}`, plus `"penalty"` for
illegal goods (paid when seized). `count` is the number of copies in the goods deck. Contracts
ask only for legal goods.

## ships/<id>.json
`{"name", "speed", "count"}`: ship tiles. Each smuggler is dealt 2 at random from all copies.

## interpol/<id>.json
`{"name", "kind": "action"|"funding", "cost", "supply", "start", "effects": {...}, "text"}`.
`supply`: copies in the market; `start`: copies in Interpol's starting deck (5 in total).
Action cards cost one of Interpol's actions; funding cards are free and may only give
`budget` (and `cards`). Effects (any mix), applied in `logic/interpol.py`:
- `cards`, `actions`, `budget`: draw / +actions / +budget
- `piece`: `"patrol"`, `"barrier"` or `"checkpoint"`: each copy owned is one piece; playing
  the card places or moves one piece of that kind. Patrols also need `move` (steps).
- `repeat: true`: play the effect of an action card already played this turn, again.

A new kind of effect needs code in `Interpol.play` / `_check_piece` (and its targets in
`Interpol.private` / `allowed`), plus a targeting step in `client/game.js` if it needs one.

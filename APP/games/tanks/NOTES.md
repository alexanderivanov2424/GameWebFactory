# Tanks: Fog of War: developer notes

Rules and the message list: the docstring at the top of `server.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py tanks`).

## Read this game to learn
- Hidden information: tank locations and mines live only on the server and reach a player through
  `private_state` (`location`, `mines`, `notes`); everyone gets them in `game_state` once the game ends.
- Turn counters with per-action costs (`TurnQueue(staggered=True)`; `COSTS`, `scan_cost`; costs are sent
  as `game.costs`).
- A setup stage inside `playing` (`stage`: `placing` then `action`).
- Host settings declared once in `SETTINGS`; one method per action through `ACTIONS`, with the checks that
  apply to every action (destroyed, placing, whose turn) in an overridden `on_game_message`.
- Random walls that never disconnect the board (`generate_walls`), drawn as CSS bars in the grid gap.
- Client: click-to-target modes (pick an action, then the board; hover preview, allowed squares
  highlighted, Cancel or Escape backs out), picking a gap between squares (nearest inner edge, used to
  build/remove walls), picking rows/columns on the board labels (scan), picking a direction by hovering a
  line from your square (blast), personal board marks kept in sessionStorage.

## Map
- `server.py`: `on_game_message()` (shared checks, then `dispatch`), one method per action (`scan`,
  `spray`, `artillery`, `blast`, `move`, `heal`, `build_wall`, `remove_wall`, `lay_mine`), `damage()`
  (applies hits and shields), `after_action()` (ends the game or starts the next turn and drops that tank's
  shield), `on_player_removed()`.
- Private details of public log entries live in `self.notes[pid][log index]` (scan result, blast
  direction, a laid mine, a mine that went off). JSON turns the int keys into strings: the client reads
  `notes[String(index)]`.
- `client/game.js`: `targeting` is the current action mode; `buildBoard()` rebuilds the grid on every state,
  `updateBoard()` only toggles highlight classes (hover, marks, previews); `allowedCells()` decides which
  squares are clickable per mode; `nearestEdge()` picks the wall gap; `renderLog()` merges `state.private.notes`
  into the public log.
- Marks are stored per room and `state.gameNumber` (`tanks.marks.<room>.<n>`) and set only by clicking squares.

## Pitfalls seen here
- A player's own action can remove them (walking onto a mine): check `pid in self.queue` before `advance`
  and pick the winner from who is left, possibly nobody (`move()`, `after_action()`).
- Public log entries must not leak secrets: a blast miss says only "miss" (not even the direction), a move
  doesn't say where, a mine that went off doesn't say whose. The actor's details go in `notes`.
- `updateBoard()` can run before `buildBoard()` for a new game, with cell arrays sized for the previous
  board: only call it after the board is rebuilt (`render()` order matters).
- Hover previews: toggle classes on existing cells; never rebuild the board on hover.
- Wall bars stick out of the cell into the grid gap and overflow the board's `overflow-x: auto` wrapper
  (a scrollbar appears): the wrapper has padding for them.
- Auto-marks were removed at the user's request: don't fill marks in automatically.
- Tanks and mines may share a square on purpose: refusing would reveal where someone is.
- A tank hit while it is next to act loses its shield at once (the next turn starts right away), so
  shields mostly matter against several hits before the tank's turn.

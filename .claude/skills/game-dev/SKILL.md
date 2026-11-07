---
name: game-dev
description: Change, debug, balance or test an existing game on the GWF games site (APP/games/<id>/) or its shared code (APP/gamekit/, APP/web/gamekit/, APP/web/shared/, APP/server/). Use for any request like "update the tank game", "add an action/card", "fix this bug", "rename X", "change costs", or to test a game. Maps where everything is (so you don't need to read whole files) and how to test without a browser or Node.
---

# Working on existing games

For a brand-new game use the `new-game` skill instead. It holds the full shared-API
rules and pitfalls; skim its sections 3–4 before larger changes.

## 1. Get oriented without reading whole files
The code is documented at the top of each file. Read those headers first; open function
bodies only for what you change.

| Question | Where to look |
|---|---|
| Rules of a game, its settings, every message the client sends | Docstring at the top of `APP/games/<id>/server.py` (`python3 -c "import ast;print(ast.get_docstring(ast.parse(open('APP/games/<id>/server.py').read())))"`) |
| How a game is built, where things are, its pitfalls | `APP/games/<id>/NOTES.md` |
| Where the rules code is | Games made from the current template: `APP/games/<id>/logic/` (its `__init__.py` docstring lists the modules; `match.py` holds `Match`) with `server.py` as the lobby side. Older games (tictactoe, tanks, peruvian-silver, arena) keep their rules in `server.py` |
| What the client receives | `game_state()` and `private_state()` in that `server.py` (with `logic/`: `Match.public()` / `Match.private(pid)`) |
| Host settings | `SETTINGS` in that `server.py` (the client draws them; no client code per setting) |
| Client layout | `grep -n "^  // ---" APP/games/<id>/client/game.js` lists its sections; element ids are in `client/index.html` |
| Rules text players read | The lobby rules paragraph in `client/index.html`, banners/targeting text and the log in `client/game.js` |
| Lobby, phases, hooks, SETTINGS, ACTIONS, timers | Header of `APP/gamekit/lobby.py` (and `settings.py`) |
| Turn order / secret simultaneous picks / card decks | Headers of `APP/gamekit/turns.py` / `APP/gamekit/choices.py` / `APP/gamekit/deck.py` |
| Validating input / loading content files | Headers of `APP/gamekit/validate.py` / `APP/gamekit/data.py` |
| Real-time games: tick loop, inputs, ping | Header of `APP/gamekit/realtime.py` |
| How state reaches clients (full state / patches / snapshots) | Header of `APP/gamekit/sync.py` |
| Client lobby API and the state shape | Header of `APP/web/gamekit/lobby.js` |
| Client real-time helpers (interpolation, keyboard input, ping) | Header of `APP/web/gamekit/realtime.js` |
| Shared UI (player list, start, lobby buttons, settings form, error banner, turn alert) | Header of `APP/web/gamekit/lobby-ui.js` |
| Base page styles and the CSS variables a game can set | Header of `APP/web/shared/theme.js` |
| Connections, reconnects, the WebSocket server | Headers of `APP/server/rooms.py`, `main.py`, `websocket.py` (platform; games don't use it directly) |
| Saved player data, guests vs. accounts, login, limits | "Saved player data" in the header of `APP/gamekit/lobby.py`; headers of `APP/server/sessions.py`, `accounts.py` |
| Turtle (emergency site shutdown) and its triggers | Header of `APP/server/turtle.py`; CLAUDE.md "Turtle" |

Games at a glance (details in each `NOTES.md`):
- **tictactoe**: the smallest full game; read it to see the whole shape of a game.
- **tanks**: hidden locations and mines, turn counters with per-action costs, click-to-target
  modes on a board with walls, private notes on public log entries.
- **peruvian-silver**: the biggest; stages inside `playing`, simultaneous secret plays,
  timed reveals, cards as JSON files (loaded in `cards.py`), forks/branches.
- **smugglers**: built with `logic/` modules; graph board from JSON maps (SVG), Interpol vs.
  smugglers, deck-building (`gamekit.Deck`), inspections that interrupt a turn, `PatchState`.
  Content files: `content/README.md`.
- **block-blast**: `logic/` modules; 9x9 boards filled with rotatable shape cards (JSON in
  `cards/`) that place tiles (types with behaviours, `logic/tiles.py`) carrying symbols
  (`logic/symbols.py`, effects in `logic/effects.py`) as separate layers, row/column clears that pay gold or deal damage, a per-player `gamekit.Deck`, a
  conveyor-priced bank, a hover ghost on the board (class toggles only), aiming at a target.
- **arena**: real-time demo (`RealtimeGame`): keyboard inputs as state, per-tick delta
  snapshots, canvas drawing with interpolation, ping shown above each player.

## 2. Make the change
- Server and client both: the server validates everything; the client only renders state.
- Constants the user specified go in the server code (`logic/` for games that have it,
  otherwise `server.py`) and reach the client through `game_state()` (e.g. `costs`, `rules`),
  never duplicated in JS.
- Games with `logic/`: rules changes go there and lobby changes (settings, messages, timers)
  in `server.py`; keep `logic/` free of lobby/`Member` code. A new module goes in the
  `logic/__init__.py` docstring and the `NOTES.md` map. Test rules on `Match` directly.
- Avoid monolithic files: one topic per module in `logic/`; split a module when it mixes topics
  or passes ~400 lines (`match.py` too) rather than adding to it.
- Games without `logic/` (tictactoe, tanks, peruvian-silver, arena): small changes stay in
  `server.py`. For a sizeable feature (a new stage, a family of card types, a subsystem), create
  `logic/__init__.py` (module list docstring) plus a `logic/<topic>.py` holding that rule code,
  called from `server.py`, instead of growing `server.py`. Don't restructure the rest of the
  game unless the user asks; note the new module in the game's `NOTES.md` map.
- A new setting is one line in `SETTINGS`; a new message is one entry in `ACTIONS` plus its
  method. Renaming a setting is the `SETTINGS` key plus any `self.settings[...]` reads. Rooms
  live in memory and reset on deploy, so no migration is needed.
- Keep the docs true in the same change: the `server.py` docstring (rules + message list),
  `logic/__init__.py`'s module list, the game's `NOTES.md`, the lobby rules paragraph in `index.html`, and anything in
  `CLAUDE.md` / skills it affects.
- Shared code: changing `APP/gamekit/` or `APP/web/gamekit/` affects every game. Run the full
  test suite, and update every game that uses what you changed. Promote anything reusable
  into gamekit (see `new-game` section 5).
- Unclear rule details: pick a sensible default and list each assumption in your final
  message instead of asking, unless the choice changes the game a lot.

## 3. Test (there's no browser and no Node in the pod)
1. `python3 -I tools/run_tests.py` (or `... run_tests.py <game-id>` while iterating): compiles
   everything, imports every game like the server does, runs the unit tests, syntax-checks all JS.
2. Add or update tests in `APP/games/<id>/tests/test_*.py` (stdlib `unittest`) for what you
   changed, using `gamekit.sim.Sim` (see its header). It drives the real lobby (join, ready,
   start, game messages, leaving, spectators), returns the error text a player would see,
   records each player's state (incl. `private`) and runs `schedule()` timers instantly
   (`auto_timers=False` + `sim.step()` to stop between a reveal and what follows).
   Cover the new rules, rejections, hidden-info leaks (check other players' and spectators'
   `state(i)`), game end (win, draw, last player destroyed by their own action) and a
   player leaving mid-game. Make them deterministic (set internals or seed `random`).
   Split tests by topic (`test_rules.py`, `test_lobby.py`, ...); fixtures several files share go
   in `tests/helpers.py` (not collected: only `test_*.py` are), imported with
   `importlib.import_module("games.<id>.tests.helpers")` (see block-blast).
   Real-time games: `Sim` never ticks on its own, so drive them with `sim.tick(n)`,
   `sim.input(i, {...})` and `sim.ping(i, rtt)`.
   Shared code gets tests in `APP/gamekit/tests/` (a tiny Game class passed to `Sim(MyGame)`).
3. Client: the JS check only catches broken brackets/strings/templates. Re-read the code
   paths you changed: element ids used in JS must exist in `index.html`, and every helper you
   call must still be defined (or come from `AppDom` / `AppLobbyUI`). Nothing else will catch
   a client bug before the user does.
4. Hand off: the user deploys on the host (`cd /home/sasha/Desktop/Dev && ./deploy.sh`; it
   runs the same checks first) and tests in two browser tabs. Give a short numbered test
   script for exactly what changed, and say plainly that the browser side is untested.

## Pitfalls seen here (game-specific ones are in each NOTES.md)
- A player's own action can remove them (e.g. walking onto a mine): check they're still in
  the `TurnQueue` before `advance`, and pick the winner from who is left (maybe nobody).
- Public log entries must not leak secrets; put the actor's private details in a per-player
  notes map keyed by log index (see tanks).
- Hover previews: toggle classes on existing cells; never rebuild the board on hover.
- JSON turns int dict keys into strings: look them up with `String(index)` in JS.
- Rule tables (which cards are playable when) belong in the game state, not copied into JS.
- Saved data (`self.save_data`): save at milestones (game end, an unlock), never per tick or per
  move in a loop; over `MAX_SAVES_PER_SESSION` saves in 10 s, or data over `MAX_DATA_BYTES`,
  turtles the whole site. Test saves with `sim.login(i, "name")` and `self.load_data(member)`.

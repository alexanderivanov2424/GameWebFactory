---
name: new-game
description: Add a new multiplayer game to the GWF games site (APP/games/<id>/) using the shared lobby (gamekit). Use when the user asks to create, add or start building a new game.
---

# Adding a multiplayer game

Read `CLAUDE.md` first, especially its **STRICT GLOBAL RULES**: no new dependencies of any
kind, HTML/JS/Python only, and no bots or whole-game playthrough tests unless the user asks.

Reference games: each `APP/games/<id>/NOTES.md` says what to learn from that game, where
things are, and its pitfalls. Read only the one closest to your game:
- `tictactoe`: the smallest full game; start here to see the whole shape.
- `tanks`: hidden information, turn counters with costs, click-to-target modes.
- `peruvian-silver`: simultaneous secret plays, timed reveals, cards as JSON.
- `smugglers`: the first `logic/`-module game; graph board as SVG, deck-building, `PatchState`.
- `block-blast`: grid placement with rotations, hover ghost, swappable market (`Choice`/`MultiChoice`).
- `marooned`: hidden role, secret votes, map built as it's explored.
- `bastion`: co-op simultaneous turns, server-side simulation sent as a replay.
- `arena`: real-time (`RealtimeGame`); start from it for continuous movement.

## 1. Pin down the design (ask only about what's genuinely unclear)
Map the request onto the shared lobby model before writing code:
- **Lobby phase:** what each player picks (→ player *options*) and what the host configures
  (→ `SETTINGS`).
- **Start conditions:** `MIN_PLAYERS`, `MAX_PLAYERS`, and anything else (→ `start_check`).
- **Play phase:** the public game state, the actions players send (→ `ACTIONS`), turn rules,
  win/draw conditions.
- **Leaving mid-game:** what happens to the game when a player leaves (→ `on_player_removed`).
- **Hidden information:** anything only some players may see (cards, roles, positions) goes in
  `private_state(member)`, never in `game_state()`. Also check what *public* events leak, such
  as hits revealing positions, and whether errors leak anything: they're private, but the
  rejection itself can be informative (e.g. refusing a move onto an occupied square reveals
  where a hidden piece is).
- **Everyone at once** (co-op build phases, shopping): skip `TurnQueue`; give each seat a
  `done` flag, let anyone act during the stage, and advance when all remaining seats are done
  (re-check after a leave).
- **Simulations** (battles, races that play out without input): run them at once on the server,
  deterministically, and send a compact replay (per-tick frames + events) for the client to
  animate, with `PatchState` so it goes out once.
- **Turn order:** use `TurnQueue`. A cost of 1 per action with the default equal start gives
  round-robin; other costs give counter-based turns. Display offsets as `(T+X)`.
  `staggered=True` (start at 1, 2, 3, ...) is only for counter games; with cost-1 round-robin
  it lets player 1 move twice in a row when there are 3+ players.
- **Simultaneous secret choices** (everyone picks, then all revealed together): use
  `SecretChoices`. Send `choices.public()` in the game state (who has picked; picks only after
  `reveal()`), and each player's own pick via `private_state`. `optional_ids` lets some
  players choose without anyone waiting for them; they only show in `public()` once they've
  picked. For picks that must stay secret forever, read them with `peek()` instead of `reveal()`.
- **Pauses** (show a reveal for a few seconds, then move on): `self.schedule(seconds, fn)`.
  It sends the state after `fn` runs and is cancelled automatically by `finish()`, a new
  start or going back to the lobby. Re-check `self.stage` in `fn`.
- **Decks of cards** (draw, discard, reshuffle; deck-building): `gamekit.Deck` keeps card
  instances `{"uid", "card"}` in a draw and a discard pile; hands and tables are the game's.
- **Content that will grow** (cards, units, levels): one JSON file per item in a folder inside
  the game (next to `server.py`, e.g. `cards/`), loaded and validated at import with
  `gamekit.data.load_json_dir` (bad files are logged and skipped), in its own module
  (`logic/cards.py`); send the definitions in the game state so the client renders any item
  without code changes.
- **Setup inside play:** for something like secret placement or drafting, use a `stage` field
  in the game state within the `playing` phase. Don't add lobby phases.
- **Real-time vs turn-based:** continuous movement (things move without waiting for turns) →
  subclass `RealtimeGame` (`APP/gamekit/realtime.py`): generate the folder with the script,
  then follow `games/arena` instead of the template's turn logic (`TurnQueue`, the turn check
  in `on_game_message`), with the simulation in `logic/` (e.g. `World.step(dt, inputs)` that
  `tick(dt)` calls with `{pid: member.input}`). Turn-based game with a big state → `SYNC = PatchState`. Otherwise
  keep the default `FullState`. Games that send deltas (`PatchState`, `Snapshots`; see
  `APP/gamekit/sync.py`) must: key changing collections by id (dicts, not lists, since a changed
  list is resent whole), never put None inside dicts (null deletes the key), and round floats
  with `quantize`. A growing log fits as a dict keyed by index plus a count.
- **Data kept between games** (stats, unlocks, progress): `self.load_data(member)` and
  `self.save_data(member, value)` (server only, one plain-JSON value per game per player). Works
  the same for guests (memory, until the tab closes) and logged-in players (disk). Save at
  milestones, never per tick: the save-rate and size limits turtle the whole site (see
  `APP/server/sessions.py`). Players can't log in or out mid-game, so the account behind a
  member is fixed while playing. In tests: `sim.login(i, "alice")`.
- **Unspecified rules:** pick a sensible default, make it a host setting if it's a number,
  and list every assumption in the final message.

## 2. Create the files
Generate the folder with the script (don't copy the templates by hand):

```
python3 -I tools/new_game.py <id> --name "Game Name" --description "One sentence for the home page."
```

It copies this skill's `templates/` (which mirror a game folder) to `APP/games/<id>/`, fills in
the id, name and description, and refuses to touch an existing folder. The result already
passes `python3 -I tools/run_tests.py <id>` (a placeholder round-robin game), so you start
from green and keep it green:

```
APP/games/<id>/
  game.json            name + description on the home page
  server.py            rules docstring + class Game(LobbyGame): the lobby side
  logic/               the game's rules, organized however the game needs
    __init__.py        docstring listing the modules in logic/
    match.py           class Match: the state of one game and the rules that change it
  client/index.html    page: shared script tags, lobby and game sections
  client/game.js       AppLobby.connect + render functions
  tests/test_<id>.py   rules tests (Match directly) + lobby tests (Sim); `-` becomes `_` in the name
  NOTES.md             developer notes
```

- The `<id>` must be lowercase letters, digits, `-` or `_`. It's also the id
  passed to `AppLobby.connect("<id>", ...)` and to `Sim("<id>")`.
- Replace every `TODO` (`grep -rn TODO APP/games/<id>`), deleting the hooks and imports you don't need.
- Changing a template: keep the `{{GAME_ID}}`, `{{GAME_NAME}}` and `{{DESCRIPTION}}`
  placeholders, and run `python3 -I tools/run_tests.py tools` (it generates a game from the
  templates and runs that game's tests).

### Where server code goes: `server.py` vs `logic/`
- `server.py` is the **lobby side**: the rules docstring (the spec and message list),
  `SETTINGS`, `ACTIONS`, player options, `start_check`, timers (`self.schedule`), saved data,
  `finish()`, and thin action methods that unpack and type-check a message, call the rules,
  then react (`check_over()` finishes the game when `match.result` is set). Keep it short.
- `logic/` is the **game itself**, a package `games.<id>.logic` with no lobby, network or
  `Member` objects: players are public ids (`"p1"`). `Match` holds one game's state and
  raises `LobbyError` for illegal moves; `public()` / `private(pid)` build what clients see.
  Tests drive it directly, which makes rule tests short and fast.
- **Avoid monolithic files.** One topic per module: `match.py` keeps the game's state and turn
  flow and calls out to the rest (`board.py` geometry, `cards.py` content loaders, `effects.py`
  one function per card/ability type, `scoring.py`, a module per stage of a multi-stage game...).
  Split a module as soon as it mixes topics or passes ~400 lines; that includes `match.py`.
  Plan the modules while pinning down the design, rather than splitting one big file later.
  Import siblings relatively (`from .board import Board`; from server.py:
  `from .logic.board import Board`), and list every module in `logic/__init__.py`'s docstring
  and the `NOTES.md` map. Content files (JSON) stay in a folder next to `server.py`.
- Never name a folder `server/` (it would shadow `server.py`) and don't import the site's
  `server` package from either; games import only `gamekit`.
- Some older games predate `logic/` and keep their rules in `server.py`. Learn their
  patterns, not their file layout, and put new rules in `logic/`.

## 3. Server (`server.py` + `logic/`): `class Game(LobbyGame)`
Import from `gamekit` only (never from `server`). See the headers of `APP/gamekit/lobby.py`
and `settings.py`. Hooks below are on `Game` in `server.py`; most delegate to `self.match`.
- `SETTINGS = {"key": Int("Label", default=, low=, high=, suffix="%")}`: host settings,
  validated (non-integers rejected, out-of-range clamped) and drawn on the client by
  `settingsForm`. A bound may name an earlier setting (`high="boardSize"`). For other
  cross-setting rules override `clean_settings`, call `super()`, then adjust.
  `Choice("Label", default="a", options={"a": "Option A", "b": "Option B"})` is a drop-down
  of fixed string values; `MultiChoice("Label", default=["a"], options={...}, low=1)` is a set
  of checkboxes whose value is a list.
- `ACTIONS = {"move": "move"}`: game messages `{"action": "move", ...}` → `self.move(member, data)`.
  Override `on_game_message` only for checks shared by every action (whose turn, stage), then
  `await self.dispatch(member, data)`.
- `default_options(member)` / `clean_options(member, options)`: per-player lobby choices.
  Enforce uniqueness here (e.g. no two players with the same color).
- `start_check()`: return a reason string if the game can't start yet.
- `start_game()`: create `self.match = Match(names, self.settings)` from `self.players`.
  Snapshot anything that must stay fixed during the game, such as names and colors, into it.
  `self.game_number` has just been increased (clients get `state.gameNumber`).
- Validate everything: action methods check message shapes and types (`gamekit.validate`:
  `whole_number`, `one_of`, `cell`; `type(x) is int`), `Match` checks the rules; either raises
  `LobbyError` to reject. Call `self.finish({...})` when the game ends (the template's
  `check_over()` does it when `match.result` is set).
- `on_player_removed(member)`: keep the game consistent (`match.remove(pid)` fixes the turn).
  Finish the game if it can't continue.
- `game_state()` → `match.public()`: JSON-safe public state. Refer to players by `member.id`
  (public id), **never** `member.client_id`.
- `private_state(member)` → `match.private(pid)`: per-member secrets. It's called for
  spectators too (return None for them). It's sent as `state.private`.
- `reset_game()`: clear the state when going back to the lobby (`self.match = None`). Also
  called from `__init__`.
- Real-time games (`RealtimeGame`, header of `APP/gamekit/realtime.py`): `tick(dt)` runs
  `TICK_RATE` times a second while playing; `on_input(member, data)` stores the latest input
  in `member.input` (inputs are held state such as keys, so don't send them as ACTIONS);
  one-off events (buy, use item) stay in `ACTIONS`. Changes go out with the next tick, not at
  once. `member.ping` is the player's round trip, for `game_state()`.

Rules and pitfalls:
- Never trust the client. Clean text with `gamekit.validate.clean_text`.
- JSON turns integer dict keys into strings. On the client, look them up with `String(index)`.
- Snapshot names when the game starts, so the log still makes sense after someone leaves.
- Settings can only change in the lobby, so reading `self.settings` during play is safe.
- A player whose action can destroy their own piece may no longer be in the `TurnQueue`
  afterwards: check `pid in self.queue` before `advance`, and decide the winner from who's
  left (possibly nobody), not from who acted.
- Rules the user called fixed are constants in `logic/` (top of the module that uses them).
  Send them in the game state for display rather than making them settings.
- Model for growth from the start: per-copy state (make items instances with a uid, not bare
  ids) and per-branch/per-player positions are cheap early and expensive to retrofit.

## 4. Client (`index.html` + `game.js`)
- Script tags (the template has them): `/shared/theme.js` first and *not* deferred, then
  deferred `/shared/home.js`, `/shared/settings.js`, `/shared/chat.js`, `/gamekit/dom.js`,
  `/gamekit/room.js`, `/gamekit/lobby.js`, `/gamekit/lobby-ui.js`, `game.js`.
- Styles: `theme.js` provides body, `main` (72px top padding for the fixed GWF and settings
  buttons), headings, `.card`/`.panel`, `.row`, `.spacer`, `.muted`, `.small`, buttons
  (`.green`, `.red`, `.plain`, `.small`) and inputs, at zero specificity. Write only
  game-specific CSS; restyle with its variables (`--gwf-bg`, `--gwf-accent`,
  `--gwf-main-width`, ...; see its header).
- Render everything from the `state` passed to `onState`: `state.game` is public, and
  `state.private` is yours only. Don't keep game logic on the client.
- Helpers: `const { $, el, svg, debounce, setInput, listNames } = AppDom;`. Build the DOM with
  `el`/`textContent` (`svg` for SVG elements, e.g. a graph board); never put player-supplied
  text into `innerHTML`.
- Use `AppLobbyUI` instead of hand-rolling: `lobbyButtons(lobby, {join, leave, ready, back})`
  and `settingsForm(element, lobby)` (both return a render function to call on every
  render), `renderPlayers` (with `afterName` for game-specific extras), `renderStart` (the
  game never starts on its own), `renderSpectators`, `connectionText`, `errorBox` (show lobby
  errors from `onError`), and for turn-based games `turnAlert(boardElement)` (call its update
  function on every render with a turn id or null).
- Per-game client data (marks, drafts, which animations already played) is keyed by
  `state.gameNumber` so it doesn't carry into the next game. Private notes (like board marks) live in sessionStorage keyed by room and `gameNumber`; never send them to the server,
  and don't fill them in automatically unless the user asks.
- Animations: rendering rebuilds the DOM, so remember which items were already shown (keyed
  by `gameNumber` and a step counter from the server) and animate only new ones, never on the
  first render after a reload. For a CSS flip, insert the face-down element, then add the
  flipped class in a double `requestAnimationFrame`.
- For board games, rebuild the board when state changes. Update highlights (hover, targets,
  marks) by toggling classes on the existing cells; rebuilding on every hover is slow and
  flickers.
- Show action controls only when it's the player's turn. Targeting modes must be cancellable
  (Cancel button and Escape) and must reset when the turn passes.
- A fixed bottom bar (like a hand of cards) needs extra bottom padding on `main` and ~100px of
  right padding so its controls stay clear of the chat tab (bottom right).
- Don't overwrite an input the user is focused on (`setInput`); debounce inputs that send on
  every keystroke. Keep dropdown labels short: "1" or "A", not "Row 1".
- Real-time pages also load `/gamekit/realtime.js` (after `lobby-ui.js`). Pass an `onSnapshot`
  handler to `AppLobby.connect` and rebuild the DOM only in `onState` (ticks would otherwise
  rebuild it 20 times a second). Draw on a canvas in `AppRealtime.loop(draw)` using
  `rt.sample(pick)` for interpolated positions, and use `rt.controls(keyMap, {enabled})` for
  keys. See `games/arena/client/`.

## 5. Promote shared code (do this every time)
Before finishing, look for anything the new game needed that another game would also need:
- **Server:** generic game behavior (a pattern two games' `logic/` would both need) goes in `APP/gamekit/` (a new module, or `lobby.py` for
  lobby/phase behavior; re-export public names in `gamekit/__init__.py`). `APP/server/` is the
  site platform (connections, rooms, chat): only change it for platform needs.
- **Client:** generic game-page code goes in `APP/web/gamekit/` as a self-contained script
  in the style of `lobby-ui.js` (header comment documents the API), added to every page's
  script tags. Site-wide page pieces (on the home page too) go in `APP/web/shared/`.
- When you move something into shared code:
  - Add tests for it in `APP/gamekit/tests/` (pass a small Game class to `Sim`).
  - Update every existing game to use it, and keep their tests passing.
  - Document the API in the module's header comment.

## 6. Update the docs (do this every time)
- The game's `server.py` docstring (rules, settings, messages), `logic/__init__.py`'s module
  list, and its `NOTES.md` (what it's a good example of, map, pitfalls you hit).
- `CLAUDE.md`: the layout tree and the lobby model if they changed.
- **This skill and its templates:** new shared APIs and general lessons only. Game-specific
  details belong in that game's `NOTES.md`, not here or in `CLAUDE.md` (add at most one line to
  the reference list above). After changing a template, run
  `python3 -I tools/run_tests.py tools` (it builds a game from them and runs its tests).

## 7. Test and hand off
`python3 -I tools/run_tests.py <id>` until it passes, then the whole suite. Write **unit tests
of individual pieces**: test rules on `Match` directly (`RulesTests` in the template: set up a
position, act, check), one test per rule, effect or scoring case. Test the lobby side with `Sim`
(turn checks, what each player and spectator receives, leaving). Don't build bots or tests
that play whole games. See the `game-dev` skill, section 3, for what to cover and how to
check the client by reading.
Then hand testing to the user:
- `cd /home/sasha/Desktop/Dev && ./deploy.sh` (it runs the checks first; if the server fails
  to start, it prints its log).
- Give a short, concrete test script. Two tabs count as two players, since the ID is per tab. Cover:
  - joining and readying, then the host clicking Start (others see "waiting for the host")
  - host-only settings and "Make host"
  - an invalid move
  - a full game to a win and to a draw
  - reloading mid-game, which should keep the seat
  - one player leaving mid-game

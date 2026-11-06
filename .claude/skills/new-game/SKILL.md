---
name: new-game
description: Add a new multiplayer game to the GWF games site (APP/games/<id>/) using the shared lobby (gamekit). Use when the user asks to create, add or start building a new game.
---

# Adding a multiplayer game

Read `CLAUDE.md` first. It holds the project rules (HTML/JS/Python only, no Node, no package
managers, no external libraries/CDNs), the layout (platform `server/` vs. the `gamekit`
library games build on) and the lobby model.

Reference games (each has a `NOTES.md` saying what to learn from it, where things are, and
the pitfalls hit while building it; read the one closest to your game):
- `APP/games/tictactoe/`: the smallest full game; player options (a color), host settings
  with a linked bound, round-robin turns.
- `APP/games/tanks/`: hidden information (`private_state`), turn counters with costs, a setup
  stage inside play, click-to-target modes with hover previews, walls between squares,
  picking gaps/rows/directions, secret objects on the board, private notes on public log
  entries, statuses lasting "until your next turn", private board marks.
- `APP/games/peruvian-silver/`: simultaneous secret plays (`SecretChoices`), timed pauses
  (`self.schedule`), a private hand with a fixed bottom bar, cards as JSON files loaded with
  `gamekit.data` in its own `cards.py` module, interrupt stages, a resolve queue for effects
  that wait on decisions, branching paths, per-copy card state, animations for new items only.

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
  rejection itself can be informative. For example, Tanks allows two tanks on one square
  because refusing would reveal where someone is.
- **Turn order:** use `TurnQueue`. A cost of 1 per action with the default equal start gives
  round-robin; other costs give counter-based turns like Tanks. Display offsets as `(T+X)`.
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
- **Content that will grow** (cards, units, levels): one JSON file per item in a folder inside
  the game, loaded and validated at import with `gamekit.data.load_json_dir` (bad files are
  logged and skipped), in its own module (e.g. `cards.py`); send the definitions in the game
  state so the client renders any item without code changes.
- **Setup inside play:** for something like secret placement or drafting, use a `stage` field
  in the game state within the `playing` phase. Don't add lobby phases.
- **Unspecified rules:** pick a sensible default, make it a host setting if it's a number,
  and list every assumption in the final message.

## 2. Create the files
Copy the templates in this skill's `templates/` folder:

| Template | Destination |
|---|---|
| `game.json` | `APP/games/<id>/game.json` |
| `server.py` | `APP/games/<id>/server.py` |
| `index.html` | `APP/games/<id>/client/index.html` |
| `game.js` | `APP/games/<id>/client/game.js` |
| `tests/test_game.py` | `APP/games/<id>/tests/test_<id>.py` |
| `NOTES.md` | `APP/games/<id>/NOTES.md` |

- The folder name `<id>` must be lowercase letters, digits, `-` or `_`. It's also the id
  passed to `AppLobby.connect("<id>", ...)` and to `Sim("<id>")`.
- The game folder is a Python package (`games.<id>`): split a large server into modules and
  import them relatively (`from .cards import CARDS`).
- Replace every `TODO` in the copies.

## 3. Server (`server.py`): `class Game(LobbyGame)`
Import from `gamekit` only (never from `server`). See the headers of `APP/gamekit/lobby.py`
and `settings.py`.
- `SETTINGS = {"key": Int("Label", default=, low=, high=, suffix="%")}`: host settings,
  validated (non-integers rejected, out-of-range clamped) and drawn on the client by
  `settingsForm`. A bound may name an earlier setting (`high="boardSize"`). For other
  cross-setting rules override `clean_settings`, call `super()`, then adjust.
- `ACTIONS = {"move": "move"}`: game messages `{"action": "move", ...}` → `self.move(member, data)`.
  Override `on_game_message` only for checks shared by every action (whose turn, stage), then
  `await self.dispatch(member, data)`.
- `default_options(member)` / `clean_options(member, options)`: per-player lobby choices.
  Enforce uniqueness here (see the color check in tictactoe).
- `start_check()`: return a reason string if the game can't start yet.
- `start_game()`: build the game state from `self.players` and `self.settings`. Snapshot
  anything that must stay fixed during the game, such as names and colors. `self.game_number`
  has just been increased (clients get `state.gameNumber`).
- Validate everything in action methods (`gamekit.validate`: `whole_number`, `one_of`, `cell`;
  `type(x) is int`, ranges) and raise `LobbyError` to reject. Call `self.finish({...})` when the game ends.
- `on_player_removed(member)`: keep the game consistent, for example by fixing the turn. Finish
  the game if it can't continue.
- `game_state()`: JSON-safe public state. Refer to players by `member.id` (public id),
  **never** `member.client_id`.
- `private_state(member)`: per-member secrets. It's called for spectators too (return None for
  them). It's sent as `state.private`.
- `reset_game()`: clear the state when going back to the lobby. Also call it from `__init__`.

Rules and pitfalls:
- Never trust the client. Clean text with `gamekit.validate.clean_text`.
- JSON turns integer dict keys into strings. On the client, look them up with `String(index)`.
- Snapshot names when the game starts, so the log still makes sense after someone leaves.
- Settings can only change in the lobby, so reading `self.settings` during play is safe.
- A player whose action can destroy their own piece may no longer be in the `TurnQueue`
  afterwards: check `pid in self.queue` before `advance`, and decide the winner from who's
  left (possibly nobody), not from who acted.
- Rules the user called fixed are constants in `server.py`. Send them in the game state for
  display rather than making them settings.
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
- Helpers: `const { $, el, debounce, setInput, listNames } = AppDom;`. Build the DOM with
  `el`/`textContent`; never put player-supplied text into `innerHTML`.
- Use `AppLobbyUI` instead of hand-rolling: `lobbyButtons(lobby, {join, leave, ready, back})`
  and `settingsForm(element, lobby)` (both return a render function to call on every
  render), `renderPlayers` (with `afterName` for game-specific extras), `renderStart` (the
  game never starts on its own), `renderSpectators`, `connectionText`, `errorBox` (show lobby
  errors from `onError`), and for turn-based games `turnAlert(boardElement)` (call its update
  function on every render with a turn id or null).
- Per-game client data (marks, drafts, which animations already played) is keyed by
  `state.gameNumber` so it doesn't carry into the next game. Private notes (like Tanks' board
  marks) live in sessionStorage keyed by room and `gameNumber`; never send them to the server,
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
- Desktop PC browsers only (mouse and keyboard); hover interactions are fine.

## 5. Promote shared code (do this every time)
Before finishing, look for anything the new game needed that another game would also need:
- **Server:** generic game behavior goes in `APP/gamekit/` (a new module, or `lobby.py` for
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
- The game's `server.py` docstring (rules, settings, messages) and its `NOTES.md` (what it's
  a good example of, map, pitfalls you hit).
- `CLAUDE.md`: the layout tree, the lobby model and the hook list if they changed.
- **This skill and its templates:** new shared APIs, and general lessons. Game-specific
  details belong in that game's `NOTES.md`, not here.

## 7. Test and hand off
`python3 -I tools/run_tests.py <id>` until it passes, then the whole suite. See the `game-dev`
skill, section 3, for what the tests should cover and how to check the client by reading.
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

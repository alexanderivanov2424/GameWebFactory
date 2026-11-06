# Project rules

A small multiplayer browser games site ("GWF") the user hosts at home for friends:
a Python standard-library WebSocket server plus plain HTML/JS pages behind nginx.

## Start here
- **Changing, fixing or testing an existing game or shared code:** use the `game-dev` skill
  (`.claude/skills/game-dev/`). It maps where everything is documented so you don't need to
  read whole files.
- **Adding a game:** use the `new-game` skill.
- Every file starts with a header comment describing it; each game's `server.py` docstring
  is its rules spec and message list, and its `NOTES.md` holds developer notes (patterns,
  map, pitfalls). Read headers before bodies.
- **Tests:** `python3 -I tools/run_tests.py [<game-id> | gamekit | server]` compiles everything,
  imports every game, runs the unit tests and syntax-checks the JS. `deploy.sh` runs it first
  and stops if it fails. Every change to a game or shared code keeps it passing and adds tests
  for new behavior.

## Dev environment
- Claude runs in a pod where `/T` is the user's `/home/sasha/Desktop/Dev`. The pod has
  Python 3 but no nginx, systemd, browser or Node. Test with `tools/run_tests.py`; the user
  runs `./deploy.sh` on the host and tests in the browser.
- The project isn't a git repository: copy files to the scratchpad before deleting them.
- Rooms live in server memory, so a deploy resets every game in progress (setting
  renames need no migration).

## Target platform
- **Desktop PC browsers only** (mouse and keyboard) for now. Phone and touch support isn't needed; don't spend effort on it, and hover-based interactions are fine. Existing responsive CSS can stay.

## Languages and tools
- Only **HTML, JavaScript, and Python** may be used (CSS inside HTML/JS is fine).
- **Node.js is not allowed**, including npm, npx, and any Node-based tooling.
- **No other general-purpose package managers** (pip, npm, yarn, cargo, gem, composer, etc.), for security reasons.
- **Avoid downloading external tools or libraries** when the functionality can reasonably be implemented directly. Prefer the browser's built-in APIs and the Python standard library.
- No external CDN scripts or stylesheets in the app.

## Project layout
Three layers: the **site platform** (games never touch it), **gamekit** (the shared library
games are built on, server and client side) and the **games** themselves.
```
APP/
  server/               Site platform (Python package `server`), run as `python3 -m server.main` from APP/
    main.py             Entry point: /ws/chat, /ws/account and /ws/game/<game-id>?room=<room-id>; imports games
    websocket.py        WebSocket protocol implementation
    rooms.py            Rooms, connections, reconnect grace period, BaseGame
    chat.py             Site-wide chat
    sessions.py         Per-tab sessions (guest or logged in), saved game data, /ws/account, save-rate limits
    accounts.py         Accounts on disk (<state>/accounts/*.json), password hashes, account/data-size limits
    turtle.py           turtle(reason): emergency shutdown of the whole site; state_dir()
    utils.py            Platform helpers (clean_text, CLIENT_ID)
    tests/              Protocol, rooms/reconnects, accounts/sessions, turtle, game loading
  gamekit/              Shared game library, server side (Python package `gamekit`). Games import only this.
    __init__.py         Re-exports: LobbyGame, LobbyError, PLAYING/FINISHED/LOBBY, Int, TurnQueue, SecretChoices,
                        RealtimeGame, FullState, PatchState, Snapshots, turtle
    lobby.py            LobbyGame: spectators/players, host, ready, phases, public + private state sync,
                        SETTINGS, ACTIONS dispatch, game_number, schedule() timers, SYNC,
                        saved player data (load_data / save_data / account_name)
    realtime.py         RealtimeGame: LobbyGame on a fixed tick (tick(dt)), buffered inputs, ping
    sync.py             FullState / PatchState / Snapshots: how state reaches clients (SYNC), merge patches
    settings.py         Int(...): host settings declared once (server validation + client inputs)
    validate.py         LobbyError and validators for player input (whole_number, one_of, cell, clean_text)
    turns.py            TurnQueue: turn counters (cost 1 per action = round-robin)
    choices.py          SecretChoices: hidden simultaneous picks (required + optional choosers), revealed all at once
    data.py             Loading JSON content files (cards, units...): bad files are logged and skipped
    sim.py              Sim: drives a game through the real lobby for tests (no network); also ticks and inputs
    tests/
  web/                  Static files, served at /
    index.html          Home page: lists games from /games.json
    shared/             Site components on every page (served at /shared/)
      theme.js          Base page styles (CSS variables, zero specificity); load first, not deferred
      home.js           "GWF" home button (top left)
      settings.js       Settings component + AppSettings API; owns the per-tab player UUID and the
                        Account tab (log in / create account / log out over /ws/account)
      chat.js           Site-wide chat component
    gamekit/            Shared game library, client side (served at /gamekit/)
      dom.js            AppDom: $, el, debounce, setInput, listNames
      room.js           AppRoom.connect(gameId, handlers): low-level game room connection
      lobby.js          AppLobby.connect(gameId, handlers): lobby client (use this for games)
      lobby-ui.js       AppLobbyUI: player list, start button/status, spectators, connection text, error banner,
                        "your turn" alert, lobbyButtons (join/leave/ready/back), settingsForm (from SETTINGS)
      realtime.js       AppRealtime.attach(lobby): interpolated sampling, keyboard controls, ping (real-time games)
  games/<game-id>/      One folder per game: a Python package `games.<game-id>`
    game.json           {"name": ..., "description": ...} shown on the home page
    server.py           class Game(LobbyGame): one instance per room. Docstring = rules spec + message list
    *.py, data folders  Optional: more modules (`from . import cards`) and content files
    client/             Game page, served at /games/<game-id>/
    tests/              unittest files (test_*.py) using gamekit.sim.Sim; not deployed
    NOTES.md            Developer notes: what to learn from it, map, pitfalls; not deployed
tools/
  run_tests.py          All checks (compile, import games, unit tests, JS syntax); deploy.sh runs it
  jscheck.py            Rough JS syntax check (no Node allowed)
deploy.sh               Runs the checks, then deploys everything; safe to re-run (--skip-tests to force);
                        installs the turtle units; refuses while turtled (--unturtle clears it)
stop.sh                 Stops app-server, nginx and any hand-started game server; ./deploy.sh restarts
.claude/skills/
  game-dev/             Working on existing games and shared code: where things are, testing, pitfalls
  new-game/             Adding a game: shared API rules, pitfalls, templates/
```
- nginx serves the static files on port 8080 and forwards `/ws/` to the Python server (systemd unit `app-server`, 127.0.0.1:8765).
- Shared components (settings, chat) must keep working no matter how a page changes. Pages only include their `<script>` tags.
- Dependencies point one way: games -> gamekit -> server. Games never import `server`, and
  `server` never imports a game except through `main.load_game`.

## Adding a game
Use the `new-game` skill (`.claude/skills/new-game/`). Each time a game is added or changed:
- **Promote shared code:** anything another game would also need goes into gamekit
  (`APP/gamekit/` for the server, `APP/web/gamekit/` for the client; site-wide page pieces in
  `APP/web/shared/`), with tests in `APP/gamekit/tests/`, and existing games are updated to use it.
- **Keep the docs true:** the game's `server.py` docstring and `NOTES.md`, this file, and the
  skills and their templates (including anything learned along the way).

Summary:
1. Create `APP/games/<game-id>/` (lowercase letters, digits, `-`, `_`).
2. Copy the templates: `game.json`, `server.py`, `client/index.html` + `client/game.js`, `tests/`, `NOTES.md`.
3. `server.py` defines `class Game(LobbyGame)` (from `gamekit`), declares `SETTINGS` (host settings)
   and `ACTIONS` (game messages), and overrides only the hooks it needs:
   `default_options`, `clean_options`, `start_check`, `start_game`, `on_game_message`
   (to add checks before `self.dispatch`), `on_player_removed`, `game_state`, `private_state`, `reset_game`.
   Raise `LobbyError("...")` to reject a request; the message is shown to that player.
   To keep data per player across games, use `self.load_data(member)` / `self.save_data(member, value)`.
4. In the client, include `/shared/theme.js` (not deferred), then `/shared/home.js`, `/shared/settings.js`,
   `/shared/chat.js`, `/gamekit/dom.js`, `/gamekit/room.js`, `/gamekit/lobby.js`, `/gamekit/lobby-ui.js`
   (deferred, in that order), then call `AppLobby.connect("<game-id>", {...})` and render from the
   `state` it delivers. theme.js's `main` leaves 72px free at the top for the fixed buttons.
   Real-time games also load `/gamekit/realtime.js` after `lobby-ui.js`.
5. Write tests in `tests/`, run `python3 -I tools/run_tests.py <game-id>`, then `./deploy.sh`.
   Examples: `games/tictactoe/` (smallest full game), `games/tanks/` (hidden information, turn
   counters, secret mines, building walls), `games/peruvian-silver/` (simultaneous secret plays,
   timed reveals, cards defined as JSON files, game split into modules). Each has a `NOTES.md`.
   `games/arena/` is the real-time example (tick loop, inputs, delta snapshots, interpolation).

## Lobby model (shared by all games)
- Every connected tab is a **member**: a **spectator** until it joins, then a **player**. Players join and leave explicitly, and only in the lobby phase.
- Phases: `lobby` (before the game) → `playing` → `finished` → host returns everyone to `lobby`.
  `state.gameNumber` counts games started in the room (key per-game client data by it).
- **Host**: the first player to join. Only the host changes settings, starts the game, passes hosting to another player, or returns to the lobby. If the host leaves, the next player in join order becomes host.
- **Ready and start**: once all players are ready (and `MIN_PLAYERS` is met and `start_check()` passes), the host clicks **Start game** to begin. Nothing starts automatically.
- **Sessions**: identity is the tab's UUID. A disconnected member keeps their place for 60 seconds (`RECONNECT_GRACE` in `rooms.py`) and shows as offline. The client remembers whether it joined, so a reload keeps the seat.
- Other clients only see members' **public ids** (`p1`, `p2`, ...). Never send client UUIDs to other clients: they act as the key to a seat.
- **State sync:** how state reaches clients is the game's `SYNC` choice: `FullState` (default: full state after each change), `PatchState` (keyframes plus patches, for big turn-based states) or `Snapshots` (per-tick deltas, used by `RealtimeGame`). Game code (`game_state()`, `private_state()`) is the same for all; see `APP/gamekit/sync.py`.

## Accounts and saved data
- Every tab is a **guest** until it logs in or creates an account in Settings → Account (self-registration).
  The login is bound to the tab's UUID on the server (`server/sessions.py`), so game rooms know who a member
  is without the page sending anything. Logging in or out is refused while the tab is playing a game.
- Games save and load data **on the server only**: `self.load_data(member)`, `self.save_data(member, value)`
  (plain JSON, one value per game per player), `self.account_name(member)`. Same calls for guests (memory,
  forgotten when the tab's session ends) and accounts (files in `/var/lib/app-server/accounts`, kept across
  deploys). On login, each game's guest data moves to the account unless the account already has data for
  that game (then the account's wins). Save at milestones, never per tick.
- Logins live in server memory: a deploy logs everyone out (accounts and their data stay).

## Turtle (emergency shutdown)
- `turtle(reason)` (`server/turtle.py`, re-exported as `gamekit.turtle`) is the shared response to anything
  that looks like abuse: the server writes a `TURTLE` marker, exits with code 77, and systemd
  (units from `deploy.sh`) stops and disables nginx and app-server, so ports 8080 and 8765 close and stay
  closed across reboots. `./deploy.sh` refuses to run until `./deploy.sh --unturtle`.
- Current triggers: more than `MAX_ACCOUNTS` accounts, saved data over `MAX_DATA_BYTES` per player
  (`accounts.py`), too many saves per session or site-wide in `SAVE_WINDOW` (`sessions.py`). Add new safety
  checks by calling `turtle(...)`; tests run in test mode (it raises `Turtled`, a BaseException), so
  test them with `assertRaises(Turtled)`.

## Settings and privacy
- Settings stay in the browser (sessionStorage) and are never sent to the server. Exceptions: the display name (sent with chat messages and when joining a game, and saved to the account while logged in), the player UUID (sent when connecting to a game room or the account socket) and the account name and password (sent only when pressing Log in / Create account). The site has no HTTPS yet, so passwords travel unencrypted; the Account tab says so.

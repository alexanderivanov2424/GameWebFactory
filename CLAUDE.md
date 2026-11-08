# Project rules

A small multiplayer browser games site ("GWF") the user hosts at home for friends:
a Python standard-library WebSocket server plus plain HTML/JS pages behind nginx.

## STRICT GLOBAL RULES (no exceptions without the user's explicit OK in this conversation)
1. **NO NEW DEPENDENCIES OF ANY KIND.** Don't add, install, download, vendor or link
   any library, package, framework, tool, font, CDN script/stylesheet or external
   service, whether it's for the app, tests, tools or dev work. That covers pip, npm/npx, Node.js,
   yarn, cargo, gem, composer, apt, curl/wget of code, and copying third-party code into the
   repo. Use only what's already here: the Python 3 standard library, the browser's built-in
   APIs, and the project's own code (`gamekit`, `server`, `tools/`). If something truly can't
   be done without a dependency, stop and ask; never add one quietly.
2. **Only HTML, JavaScript and Python** (CSS inside HTML/JS is fine). No other languages,
   build steps, transpilers or bundlers.
3. **Don't build bots, AI players or automated full-game playthroughs** (including throwaway
   scratch ones for balancing or testing) unless the user explicitly asks for one. They burn
   a lot of tokens for little value. Test with focused **unit tests of individual pieces**
   (one rule, one card effect, one scoring function, one validator, one lobby hook) that set up
   a specific position and check the result. For balance questions, reason from the numbers
   and give the user your reasoning instead of simulating games.

## Start here
- **Changing, fixing or testing an existing game or shared code:** use the `game-dev` skill.
  It maps where everything is documented so you don't need to read whole files.
- **Adding a game:** use the `new-game` skill. It generates the folder with `tools/new_game.py`.
- **Player feedback:** use the `feedback` skill (implements `Feedback/<game>/`, or builds one new game
  from `Feedback/new_game/`, then deletes the feedback it used).
- Every file starts with a header comment describing it. Each game's `server.py` docstring
  is its rules spec and message list, and its `NOTES.md` holds developer notes (patterns,
  map, pitfalls). Read headers before bodies.
- **Modules, not one big file:** a game's rules go in its `logic/` package, one topic per
  module. `server.py` stays the thin lobby side. Split a module when it mixes topics or
  passes ~400 lines.
- **Tests:** `python3 -I tools/run_tests.py [<game-id> | gamekit | server | tools]` compiles
  everything, imports every game, runs the unit tests and syntax-checks the JS. `deploy.sh`
  runs it first and stops if it fails. Every change keeps it passing and adds unit tests
  for new behavior.
- **Each change:** move anything another game would also need into gamekit (with tests,
  updating the games that use it), and keep the docs true in the same change (see the skills).

## Dev environment
- Claude runs in a pod where `/T` is the user's `/home/sasha/Desktop/Dev`. The pod has
  Python 3 but no nginx, systemd, browser or Node. Test with `tools/run_tests.py`. The user
  runs `./deploy.sh` on the host and tests in the browser.
- The project is a git repository, but commit only when asked. Before deleting anything that
  isn't committed, copy it to the scratchpad.
- Rooms live in server memory, so a deploy resets every game in progress (setting
  renames need no migration).
- **Desktop PC browsers only** (mouse and keyboard). Don't spend effort on phone or touch
  support. Hover interactions are fine, and existing responsive CSS can stay.

## Host scripts (deploy.sh, stop.sh, accounts.sh, tools/)
- **Keep work inside the project folder** (`/home/sasha/Desktop/Dev`) as much as possible: data, state,
  backups, generated files and helper scripts go in folders under it (git-ignored if they hold data, like
  `Accounts/`), not in `/var`, `/opt`, `/etc`, `/usr/local` or elsewhere in the user's home.
- Reach outside it only where the system requires it. Today that's nginx's site config, the systemd units,
  the deployed copies (`/var/www/app`, `/opt/app`), `/usr/local/sbin/app-turtle` and `/var/lib/app-server`
  (the TURTLE marker). Don't add a new outside path unless the project folder can't do the job; list every
  outside path a script touches, and why, in its header.
- When changing a script, mention in your final message any outside path it uses that could move into
  the project; don't move it without asking.
- Services that use project data run as the folder's owner, sandboxed to just the folders they need (see
  the `app-server` unit in deploy.sh). New scripts: logic in Python under `tools/`, a thin bash wrapper at
  the top level, and sudo only for the steps that need it.

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
    accounts.py         Accounts on disk (accounts_dir()/*.json), password hashes, account/data-size limits
    feedback.py         /ws/feedback: Settings -> Feedback text saved to Feedback/<game>/<uuid>_<name>.txt; limits
    turtle.py           turtle(reason): emergency shutdown of the whole site; state_dir()
    utils.py            Platform helpers (clean_text, CLIENT_ID)
    tests/              Protocol, rooms/reconnects, accounts/sessions, turtle, game loading
  gamekit/              Shared game library, server side (Python package `gamekit`). Games import only this.
    __init__.py         Re-exports: LobbyGame, LobbyError, PLAYING/FINISHED/LOBBY, Int, Choice, MultiChoice, TurnQueue, SecretChoices,
                        Deck, RealtimeGame, FullState, PatchState, Snapshots, turtle
    lobby.py            LobbyGame: spectators/players, host, ready, phases, public + private state sync,
                        SETTINGS, ACTIONS dispatch, game_number, schedule() timers, SYNC,
                        saved player data (load_data / save_data / account_name)
    realtime.py         RealtimeGame: LobbyGame on a fixed tick (tick(dt)), buffered inputs, ping
    sync.py             FullState / PatchState / Snapshots: how state reaches clients (SYNC), merge patches
    settings.py         Int(...), Choice(...), MultiChoice(...): host settings declared once (server validation + client inputs)
    validate.py         LobbyError and validators for player input (whole_number, one_of, cell, clean_text)
    turns.py            TurnQueue: turn counters (cost 1 per action = round-robin)
    choices.py          SecretChoices: hidden simultaneous picks (required + optional choosers), revealed all at once
    deck.py             Deck: shuffled draw pile + discard pile of card instances (uids), reshuffles when empty
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
      dom.js            AppDom: $, el, svg, debounce, setInput, listNames
      room.js           AppRoom.connect(gameId, handlers): low-level game room connection
      lobby.js          AppLobby.connect(gameId, handlers): lobby client (use this for games)
      lobby-ui.js       AppLobbyUI: player list, start button/status, spectators, connection text, error banner,
                        "your turn" alert, lobbyButtons (join/leave/ready/back), settingsForm (from SETTINGS)
      realtime.js       AppRealtime.attach(lobby): interpolated sampling, keyboard controls, ping (real-time games)
  games/<game-id>/      One folder per game: a Python package `games.<game-id>`
    game.json           {"name": ..., "description": ...} shown on the home page
    server.py           class Game(LobbyGame): one instance per room, the lobby side (settings, messages,
                        timers). Docstring = rules spec + message list
    logic/              The game's rules (package games.<id>.logic): match.py's Match holds one game's state;
                        more modules by topic as it grows (board.py, cards.py...). No lobby/Member code.
                        Older games predate it and keep their rules in server.py (+ peruvian-silver's cards.py)
    data folders        Optional content files (e.g. cards/*.json) next to server.py, loaded from logic/
    client/             Game page, served at /games/<game-id>/
    tests/              unittest files (test_*.py) using gamekit.sim.Sim; not deployed
    NOTES.md            Developer notes: what to learn from it, map, pitfalls; not deployed
tools/
  run_tests.py          All checks (compile, import games, unit tests, JS syntax); deploy.sh runs it
  jscheck.py            Rough JS syntax check (no Node allowed)
  new_game.py           Creates APP/games/<id>/ from the new-game skill's templates (agents use it)
  accounts.py           Account manager behind accounts.sh (list/find, select, show, delete)
  tests/                Tests for the tools (run_tests.py runs them too: `run_tests.py tools`)
deploy.sh               Runs the checks, then deploys everything; safe to re-run (--skip-tests to force);
                        installs the turtle units; refuses while turtled (--unturtle clears it);
                        creates Accounts/ and Feedback/ and runs app-server as the folder's owner
Accounts/               Account files (created by deploy.sh; git-ignored, never deployed or edited by hand
                        while app-server runs)
Feedback/               Player feedback, Feedback/<game id, "site" or "new_game">/<uuid>_<name>.txt (created
                        by deploy.sh; git-ignored, never deployed; the feedback skill deletes what it uses)
stop.sh                 Stops app-server, nginx and any hand-started game server; ./deploy.sh restarts
accounts.sh             Host account manager: find, select, show and delete accounts; deleting
                        restarts app-server (it keeps accounts in memory); no backup is kept
.claude/skills/
  feedback/             Implementing one game's feedback, or one new game from Feedback/new_game/, then deleting it
  game-dev/             Working on existing games and shared code: where things are, testing, pitfalls
  new-game/             Adding a game: shared API rules, pitfalls, templates/ (mirror a game folder; filled in
                        by tools/new_game.py, whose tests build a game from them and run its tests)
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
- **Keep the docs true:** the game's `server.py` docstring, `logic/__init__.py` module list and `NOTES.md`, this file, and the
  skills and their templates (including anything learned along the way).

Summary:
1. Generate the folder: `python3 -I tools/new_game.py <game-id> --name "Name" --description "..."`
   (id: lowercase letters, digits, `-`, `_`). It creates `game.json`, `server.py`, `logic/`,
   `client/index.html` + `client/game.js`, `tests/` and `NOTES.md`, already passing the tests.
2. Put the rules in `logic/` (`Match` in `logic/match.py`, more modules as needed; players are
   public ids, no lobby code) and keep `server.py` as the thin lobby side.
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
   `games/smugglers/` is the first game built with `logic/` modules: a graph board from JSON
   map files drawn as SVG, asymmetric roles, deck-building (`Deck`), an interrupt inside a
   turn, and `PatchState`.
   `games/block-blast/` (`logic/` modules): a personal deck per player (`Deck`), polyomino
   cards from JSON placed with rotations (never mirrored), a hover ghost with a "would clear"
   preview on a grid, a market whose type the host picks (`logic/market/`: a `Market` base class
   with swappable subclasses, settings built from their registry with `Choice`), card packs
   from JSON files the host ticks (`MultiChoice`).
   `games/marooned/` (`logic/` modules): a hidden-role game (one secret Imposter), a grid map
   built as it's explored (draw 2 tile cards, place 1), per-player stats feeding end scoring and
   secret objectives (JSON with a `check` key -> scoring function), hidden picks that only work
   like a physical game (secret die rolls you may under-report, a Secret Hitler style card
   hand-off between two players), a nightly secret vote with only the tally shown, `PatchState`.
   `games/gilded-trail/` (`logic/` modules): a hex map generated from a seed (preset JSON maps
   or a random one) drawn as SVG, deck-building with a shared market and reserve (`Deck` per
   player), action cards that leave a pending choice inside the turn, and the server sending
   every legal step so the client holds no rules; `PatchState`.

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
  forgotten when the tab's session ends) and accounts (files in `Accounts/` in the Dev folder, kept across
  deploys). On login, each game's guest data moves to the account unless the account already has data for
  that game (then the account's wins). Save at milestones, never per tick.
- Logins live in server memory: a deploy logs everyone out (accounts and their data stay).
- Account files: `Accounts/<lowercase name>.json` next to `APP/` (git-ignored, mode 700). The server finds
  the folder through `$ACCOUNTS_DIRECTORY` (`accounts_dir()` in `server/accounts.py`; without it,
  `<state dir>/accounts`, e.g. `APP/.data/accounts` for a hand-started server). deploy.sh runs app-server
  as the Dev folder's owner so the files are theirs, sandboxed (`ProtectHome=tmpfs` +
  `BindPaths=` Accounts/ and Feedback/ only, `ProtectSystem=strict`); the state dir (`/var/lib/app-server`) keeps only
  the TURTLE marker.
- The server loads every account at startup and rewrites an account's file on each save, so account
  files are only changed with the server stopped. `./accounts.sh` (on the host) does that for deletes.

## Turtle (emergency shutdown)
- `turtle(reason)` (`server/turtle.py`, re-exported as `gamekit.turtle`) is the shared response to anything
  that looks like abuse: the server writes a `TURTLE` marker, exits with code 77, and systemd
  (units from `deploy.sh`) stops and disables nginx and app-server, so ports 8080 and 8765 close and stay
  closed across reboots. `./deploy.sh` refuses to run until `./deploy.sh --unturtle`.
- Current triggers: more than `MAX_ACCOUNTS` accounts, saved data over `MAX_DATA_BYTES` per player
  (`accounts.py`), too many saves per session or site-wide in `SAVE_WINDOW` (`sessions.py`), feedback over 50 KB,
  sent too often (per tab or site-wide) or a Feedback/ folder over 100 MB (`feedback.py`). Add new safety
  checks by calling `turtle(...)`; tests run in test mode (it raises `Turtled`, a BaseException), so
  test them with `assertRaises(Turtled)`.

## Settings and privacy
- Settings stay in the browser (sessionStorage) and are never sent to the server. Exceptions: the display name (sent with chat messages and when joining a game, and saved to the account while logged in), the player UUID (sent when connecting to a game room or the account socket), the account name and password (sent only when pressing Log in / Create account) and feedback text with the display name and chosen game (sent only when pressing Submit in the Feedback tab). The site has no HTTPS yet, so passwords travel unencrypted; the Account tab says so.

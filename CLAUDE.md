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
- **Player feedback:** use the `feedback` skill (implements `ExternalWrite/Feedback/<game>/`, several games at once
  with one subagent per game on request, or builds one new game from `ExternalWrite/Feedback/new_game/`, then deletes
  the feedback it used).
- Every file starts with a header comment describing it. Each game's `server.py` docstring
  is its rules spec and message list, and its `NOTES.md` holds developer notes (patterns,
  map, pitfalls). Read headers before bodies.
- **Modules, not one big file:** a game's rules go in its `logic/` package, one topic per
  module. `server.py` stays the thin lobby side. Split a module when it mixes topics or
  passes ~400 lines.
- **Tests:** `python3 -I tools/run_tests.py [<game-id> | gamekit | server | tools]` compiles
  everything, imports every game, runs the unit tests and syntax-checks the JS. The site's
  `startup.sh` script runs it first (on a snapshot, as root) and stops if it fails. Every change keeps it passing and adds unit tests
  for new behavior.
- **Each change:** move anything another game would also need into gamekit (with tests,
  updating the games that use it), and keep the docs true in the same change (see the skills).

## Dev environment
- Claude runs in a pod where `/T` is the user's `/home/sasha/Desktop/Dev`. The pod has
  Python 3 but no nginx, systemd, browser or Node. Test with `tools/run_tests.py`. The user
  starts the site on the host (`sudo ./startup.sh` in SiteManagement/, see below) and tests in the browser.
- The project is a git repository, but commit only when asked. Before deleting anything that
  isn't committed, copy it to the scratchpad.
- Rooms live in server memory, so restarting the site resets every game in progress (setting
  renames need no migration).
- **Desktop PC browsers only** (mouse and keyboard), except AdditionalPages/ pages, which are for phones too. Don't spend effort on phone or touch
  support. Hover interactions are fine, and existing responsive CSS can stay.

## Running the site (SiteManagement/, outside the Dev folder)
- The site runs as one rootless **podman pod `gwf`** owned by the locked-down `gwf` user, plain HTTP on
  port 8080 (the router forwards external 80 to it). Two containers: `gwf-app` (the game server and every
  additional page's server, started by `launcher.py`) and `gwf-nginx` (static files, `/ws/`, the pages).
  Both have a read-only root filesystem, no capabilities and no automatic restarts.
- `sudo ./startup.sh [--skip-tests] [--unturtle]` and `sudo ./shutdown.sh` live in **SiteManagement/, which the
  user keeps outside the Dev folder** so nothing that can write to Dev changes what runs as root. Claude
  can't see or edit them from the pod unless the user shares them. Their headers list every path they use.
- `startup.sh` snapshots the code, runs `tools/run_tests.py`, `tools/additional_pages.py` and
  `tools/games_list.py` on the snapshot with the host's python3 (as root: keep tests free of side
  effects outside temp folders), builds `Deployed/` (git-ignored, read-only in the containers, rebuilt every start),
  writes the nginx config there and starts the pod. If the app container stops for any reason (crash,
  turtle), a watcher stops the whole pod. Nothing restarts by itself, not even after a reboot.
- **No outbound connections:** before starting the pod, `startup.sh` loads an nftables table (`inet gwf_egress`)
  that rejects every connection the `gwf` user starts (LAN, internet, Pi-hole); replies to visitors pass. The site
  must never need to call out (no fetching URLs, no outside APIs); a feature that would is a question for the user.
- **`ExternalWrite/` is the only writable folder** (git-ignored; mounted into `gwf-app` only; written by
  `gwf`; ACLs set once by hand, not by the scripts, give `gwf` and `sasha` read/write, inherited by new files, so
  this pod can read it): `Accounts/`, `Feedback/`, `State/` (TURTLE marker) and `AdditionalPages/<id>/`
  (each page server's data). Anything new the running site must write goes in there.
- **Keep work inside the project folder** (`/home/sasha/Desktop/Dev`): data, state, generated files and
  helper scripts go in folders under it, not in `/var`, `/opt`, `/etc`, `/usr/local` or elsewhere in the
  user's home. Outside paths today: SiteManagement/ itself, and gwf's podman storage and runtime folder.
- `SiteManagement/accounts.sh` (host account manager, run without sudo as `sasha`) is a thin
  wrapper around `tools/accounts.py` in Dev. New host scripts follow the same pattern: logic in Python under
  `tools/`, a thin bash wrapper in SiteManagement/, and sudo only for the steps that need it.

## Project layout
Three layers: the **site platform** (games never touch it), **gamekit** (the shared library
games are built on, server and client side) and the **games** themselves.
```
APP/
  server/               Site platform (Python package `server`), run as `python3 -m server.main` from APP/
    main.py             Entry point: /ws/chat, /ws/account, /ws/feedback, /ws/admin and /ws/game/<game-id>?room=<room-id>; imports games
    websocket.py        WebSocket protocol implementation
    rooms.py            Rooms, connections, reconnect grace period, BaseGame
    chat.py             Site-wide chat
    sessions.py         Per-tab sessions (guest or logged in), saved game data, /ws/account, save-rate limits
    accounts.py         Accounts on disk (accounts_dir()/*.json), password hashes, account/data-size limits
    feedback.py         /ws/feedback: Settings -> Feedback text saved to Feedback/<game>/<uuid>_<name>.txt; limits
    admin.py            /ws/admin: password-gated, read-only admin view of accounts, feedback, sessions, rooms
    turtle.py           turtle(reason): emergency shutdown of the whole site; state_dir()
    utils.py            Platform helpers (clean_text, CLIENT_ID)
    tests/              Protocol, rooms/reconnects, accounts/sessions, turtle, game loading
  gamekit/              Shared game library, server side (Python package `gamekit`). Games import only this.
    __init__.py         Re-exports: LobbyGame, LobbyError, PLAYING/FINISHED/LOBBY, Int, Choice, MultiChoice, TurnQueue, SecretChoices,
                        Deck, RealtimeGame, FullState, PatchState, Snapshots, turtle
                        (gamekit.hexes and gamekit.shapes are imported directly)
    lobby.py            LobbyGame: spectators/players, host, ready, phases, end-game vote, public + private state sync,
                        SETTINGS, ACTIONS dispatch, game_number, schedule() timers, SYNC,
                        saved player data (load_data / save_data / account_name)
    realtime.py         RealtimeGame: LobbyGame on a fixed tick (tick(dt)), buffered inputs, ping
    sync.py             FullState / PatchState / Snapshots: how state reaches clients (SYNC), merge patches
    settings.py         Int(...), Choice(...), MultiChoice(...): host settings declared once (server validation + client inputs)
    validate.py         LobbyError and validators for player input (whole_number, one_of, cell, clean_text)
    turns.py            TurnQueue: turn counters (cost 1 per action = round-robin)
    choices.py          SecretChoices: hidden simultaneous picks (required + optional choosers), revealed all at once
    deck.py             Deck: shuffled draw pile + discard pile of card instances (uids), reshuffles when empty
    shapes.py           Polyomino shapes: parse rows of '#', turn them, list the 4 rotations (never mirrored)
    hexes.py            Hex grid geometry (axial "q,r" keys): distance, neighbours, disk/ring maps, 6 rotations of hex shapes
    data.py             Loading JSON content files (cards, units...): bad files are logged and skipped
    sim.py              Sim: drives a game through the real lobby for tests (no network); also ticks and inputs
    tests/
  web/                  Static files, served at /
    index.html          Home page: lists games from /games.json (player-count badge top right)
    shared/             Site components on every page (served at /shared/)
      theme.js          Base page styles (CSS variables, zero specificity); load first, not deferred
      home.js           "GWF" home button (top left)
      settings.js       Settings component + AppSettings API; owns the per-tab player UUID and the
                        Account tab (log in / create account / log out over /ws/account); a game adds
                        its own player settings tab with AppSettings.addPageSettings
      chat.js           Site-wide chat component
      admin.js          Admin view button + dialog (view only); not in pages: settings.js loads it while
                        Settings -> Settings -> Enable Admin Mode holds a password
    gamekit/            Shared game library, client side (served at /gamekit/)
      dom.js            AppDom: $, el, svg, fill, debounce, setInput, listNames
      room.js           AppRoom.connect(gameId, handlers): low-level game room connection
      lobby.js          AppLobby.connect(gameId, handlers): lobby client (use this for games)
      lobby-ui.js       AppLobbyUI: player list, start button/status, spectators, connection text, error banner,
                        "your turn" alert, lobbyButtons (join/leave/ready/back), settingsForm (from SETTINGS),
                        endGameButton (the "End game" vote, on every game page)
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
  run_tests.py          All checks (compile, import games, unit tests, JS syntax); startup.sh runs it
  jscheck.py            Rough JS syntax check (no Node allowed)
  new_game.py           Creates APP/games/<id>/ from the new-game skill's templates (agents use it)
  accounts.py           Account manager behind SiteManagement/accounts.sh (list/find, select, show, delete)
  games_list.py         Builds games.json for the home page (name, description, player-count badge
                        from each Game's MIN_PLAYERS/MAX_PLAYERS); startup.sh runs it
  additional_pages.py   Lists and checks AdditionalPages/ for startup.sh and run_tests.py (layout rules in its header)
  tests/                Tests for the tools (run_tests.py runs them too: `run_tests.py tools`)
AdditionalPages/        Extra standalone pages served with the games site but never linked from it.
                        <id>/ is served at /<id>/: web/ (static, strict CSP: no inline scripts), optional
                        server.py + site.json (its own stdlib HTTP server for /<id>/api/ on 127.0.0.1:<port>,
                        run in gwf-app next to the game server; its data goes in $SITE_DATA =
                        ExternalWrite/AdditionalPages/<id>/). They don't use theme/settings/chat or gamekit.
                        Phone support is wanted here. startup.sh and shutdown.sh start and stop them with the site.
  food-list/            Secret shared shopping lists (/food-list). Everything about an item (name, tags, notes, unit,
                        photos) is saved once for all lists and kept after it leaves a list (names lowercase and unique,
                        suggested when adding); a list entry has only its checkmark and amount. The title opens the
                        lists screen: New list, a Global list of every saved item (edit everything, default amounts,
                        delete items for good), then each list with Edit (name, template, delete) and, on templates,
                        Copy (amounts copied; copies show their template's name), then New tag and every tag with Edit (name,
                        colour, delete). Coloured tags; edit/view modes, where view mode filters by tags (items having all the selected ones).
                        Photos are decoded in the browser and sent as raw RGB; images.py writes a fresh PNG from them.
ExternalWrite/          Everything the running site writes; the only writable mount (git-ignored, owner gwf):
  Accounts/             Account files (never edited by hand while the site runs)
  Feedback/             Player feedback, <game id, "site" or "new_game">/<uuid>_<name>.txt (the feedback
                        skill deletes what it uses)
  State/                TURTLE marker
  AdditionalPages/<id>/ Each additional page server's data
Deployed/               Built by startup.sh on every start (git-ignored): the code, web files and nginx.conf
                        the pod runs. Never edit it.
.claude/skills/
  feedback/             Implementing one game's feedback (or several, one subagent each), or one new game from ExternalWrite/Feedback/new_game/, then deleting it
  game-dev/             Working on existing games and shared code: where things are, testing, pitfalls
  new-game/             Adding a game: shared API rules, pitfalls, templates/ (mirror a game folder; filled in
                        by tools/new_game.py, whose tests build a game from them and run its tests)
```
- nginx serves the static files on port 8080 and forwards `/ws/` to the Python server (127.0.0.1:8765 in the same pod).
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
   (to add checks before `self.dispatch`), `on_player_removed`, `game_state`, `private_state`, `reset_game`,
   `lobby_game_state` (info shown in the lobby as `state.game`, e.g. a saved run).
   Raise `LobbyError("...")` to reject a request; the message is shown to that player.
   To keep data per player across games, use `self.load_data(member)` / `self.save_data(member, value)`.
4. In the client, include `/shared/theme.js` (not deferred), then `/shared/home.js`, `/shared/settings.js`,
   `/shared/chat.js`, `/gamekit/dom.js`, `/gamekit/room.js`, `/gamekit/lobby.js`, `/gamekit/lobby-ui.js`
   (deferred, in that order), then call `AppLobby.connect("<game-id>", {...})` and render from the
   `state` it delivers. theme.js's `main` leaves 72px free at the top for the fixed buttons.
   Real-time games also load `/gamekit/realtime.js` after `lobby-ui.js`.
5. Write tests in `tests/`, run `python3 -I tools/run_tests.py <game-id>`; the user restarts the site.
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
   `games/bastion/` (`logic/` modules): a city-builder where each player runs their own city and
   trades with the others (endless for now; enemy modules kept but dormant): a setup phase in
   turn order, then simultaneous phases each round (place units on owned one-tile buildings,
   build tokens, gathering tiles; resolution with automatic jobs plus per-player prompts answered
   one by one; planning with royal decrees, blueprints, Orders and Trade), a two-half persistent
   market, per-player resources and upkeep, reach-limited placement; `PatchState`. Its playtest
   bots (`tests/bots.py`, `tests/playtest.py`) are disabled until rewritten for the redesign.
   `games/gilded-trail/` (`logic/` modules): a hex map generated from a seed (preset JSON maps
   or a random one) drawn as SVG, deck-building with a shared market and reserve (`Deck` per
   player), action cards that leave a pending choice inside the turn, and the server sending
   every legal step so the client holds no rules; `PatchState`.
   `games/deep-colony/` (`RealtimeGame`, `logic/` modules): a co-op colony sim where players
   never control a unit: shared orders tagged by player, shared pause/speed, live cursors as
   realtime input, a cell simulation (gas, liquid, heat, germs, decor) sent as row strings over
   `Snapshots`, power/pipe networks, and colonists choosing chores on their own.
   `games/bastion2/` (`logic/` modules): Bastion as a deck-building city-builder (no units, no
   terrain, enemies hidden): a play area with per-turn resource counters, upkeep cards that punish
   being discarded, builds that complete at the end of the turn, structure actions, an unbounded
   grid shown as a pannable/zoomable floating map with the HUD around the screen edges, and turns
   either everyone at once or one at a time (a setting); `PatchState`.
   `games/hex-realms/` (`logic/` modules): a civilization game on a random hex map (`gamekit.hexes`):
   everyone plans in secret at once, then all orders resolve together (simultaneous step-by-step
   movement where units that meet fight with dice, sieges, towers), multi-cell structures staffed
   by population and built over several turns by idle people (construction sites), goods kept in
   stores, no roads (free first-come territory around each Town Hall, plus weak land bought with gold, 1 gold upkeep per cell, that enemy units next to it or being cut off take away), standing orders kept across turns (Explore,
   Fight, Pillage, multi-turn Travel), a tech tree popup, own units passing through each other, fog of war sent as each
   member's private map view, a Settlers start (found your own first city), territory, advances
   bought with science or faith, an optional turn timer (`schedule`), bots in extra seats (a
   setting; the user asked for them) planning through the same orders, standing trades set per market,
   every sentence players read in one file (`client/text.js`); `PatchState`.
   `games/orbit-run/` ("Planet Jumpers", `logic/` modules): a co-op trick-taking game for 3-5 played as a run of
   missions: a task draft from the captain, follow-suit tricks with a timed pause on each full trick,
   ending a mission early once every task is secured (tasks flag `can_fail_when_done` by hand),
   mission and task cards as JSON (3 mission decks), and a run (ship resources, missions played)
   saved for the host with `save_data` and continued from a later game (`lobby_game_state` shows it).
   `games/snowbound/` (`RealtimeGame`, `logic/` modules): a co-op idle game on a huge grid (up to 384x384
   lots as dirty row strings): you walk a character (client-side prediction mirroring the server's
   collision), full-screen canvas with a HUD, every machine its own unit with its own behaviour
   (`logic/machines.py`), behaviour-flag upgrades, per-player area-of-interest unit sync, survival near heat,
   machines hauling snow to drop points over a player-built road network (levelled roads, incremental route
   fields), processors chained side by side and sleds selling goods, hidden one-of-a-kind landmarks with
   unique rewards.
   `games/motorways/` ("Metro Lanes", `RealtimeGame`, `logic/` modules): co-op Mini Motorways in one shared
   city: players draw road tiles they own (8-direction links, bridges/tunnels, motorways, roundabouts,
   lights) from their own stock, cars route over the graph with lanes and junction capacity, each trip's
   points split by who built the road, the same weekly offers for everyone during a shared pick pause,
   and a shared loss when any shop overflows.

## Lobby model (shared by all games)
- Every connected tab is a **member**: a **spectator** until it joins, then a **player**. Players join and leave explicitly, and only in the lobby phase.
- Phases: `lobby` (before the game) → `playing` → `finished` → host returns everyone to `lobby`.
- **Ending early:** during play every page shows an "End game" button (top right, left of Settings;
  `AppLobbyUI.endGameButton`, added by `lobby.js`). Once every player has voted, everyone goes back to the
  lobby (`end_vote` in `gamekit/lobby.py`; `reset_game` runs). Games need no code for it.
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
  forgotten when the tab's session ends) and accounts (files in `ExternalWrite/Accounts/` in the Dev folder, kept across
  restarts). On login, each game's guest data moves to the account unless the account already has data for
  that game (then the account's wins). Save at milestones, never per tick.
- Staying logged in: the server keeps logins in memory, and each tab also keeps a signed login token
  (sessionStorage, 30 days, key in `ExternalWrite/Accounts/.login-key`) that logs it back in after a reload, a long
  disconnect or a restart ("resume" in `server/sessions.py`). Deleting `.login-key` logs every tab out.
- Account files: `ExternalWrite/Accounts/<lowercase name>.json` (git-ignored, owned by gwf). The server finds
  the folder through `$ACCOUNTS_DIRECTORY` (`accounts_dir()` in `server/accounts.py`; without it,
  `<state dir>/accounts`, e.g. `APP/.data/accounts` for a hand-started server). The state dir
  (`$STATE_DIRECTORY`, `ExternalWrite/State/` on the host) keeps only the TURTLE marker.
- The server loads every account at startup and rewrites an account's file on each save, so account
  files are only changed with the site stopped. `SiteManagement/accounts.sh` (on the host) refuses to delete while it runs.

## Turtle (emergency shutdown)
- `turtle(reason)` (`server/turtle.py`, re-exported as `gamekit.turtle`) is the shared response to anything
  that looks like abuse: the server writes a `TURTLE` marker (`ExternalWrite/State/`), exits with code 77, its container
  stops and startup.sh's watcher stops the whole pod, so port 8080 closes (nothing restarts by itself).
  `startup.sh` refuses to run until `startup.sh --unturtle`.
- Current triggers: more than `MAX_ACCOUNTS` accounts, saved data over `MAX_DATA_BYTES` per player
  (`accounts.py`), too many saves per session or site-wide in `SAVE_WINDOW` (`sessions.py`), feedback over 50 KB,
  sent too often (per tab or site-wide) or a feedback folder over 100 MB (`feedback.py`). Add new safety
  checks by calling `turtle(...)`; tests run in test mode (it raises `Turtled`, a BaseException), so
  test them with `assertRaises(Turtled)`.

## Settings and privacy
- Settings stay in the browser (sessionStorage) and are never sent to the server. Exceptions: the display name (sent with chat messages and when joining a game, and saved to the account while logged in), the player UUID (sent when connecting to a game room or the account socket), the account name and password (sent only when pressing Log in / Create account), the login token the server gave the tab (sent when the account socket connects) and feedback text with the display name and chosen game (sent only when pressing Submit in the Feedback tab), and the admin password (Settings -> Settings -> Enable Admin Mode; sent to /ws/admin, which checks it and then answers read-only admin requests). The site has no HTTPS yet, so passwords travel unencrypted; the Account tab says so.
- **Player settings for a game** (not the host's `SETTINGS`): `AppSettings.addPageSettings(label, fields)`
  adds a tab to the Settings dialog (selects and checkboxes, keys starting with the game id); they stay in the
  browser like any setting. Example: Hex Realms' combat replay speed / skip (`client/replay.js`).
- **Admin view** (`server/admin.py`, `web/shared/admin.js`): **turned off on the live site**: nginx answers
  `/ws/admin` with 404 (startup.sh), so the site gives nobody special access. The code stays (a hand-started
  server still has it). View only, and not meant to be secure (one shared password, `ADMIN_PASSWORD`). Never add actions that change anything there without the user's OK, never send
  password hashes, and only shortened client UUIDs (a full one is a seat key). Games show up in the Rooms tab
  through `admin_info()` (`BaseGame` default; `LobbyGame` lists members, phase, host and settings).

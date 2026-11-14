# Bastion: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files and their
fields: `content/README.md`. Tests: `tests/` (`python3 -I tools/run_tests.py bastion`).

History: a tower-defense game (2026-11-08), then a co-op worker-placement city-builder with a
shared stockpile, hauling, upgrades and enemy cards (v3/v4, 2026-11-09). On 2026-11-09 (later) it
was redesigned from the user's spec (`REDESIGN_PROMPT.md`, kept next to this file): each player
runs their own city with their own resources, the focus is trading, every phase but setup is
simultaneous, and enemies are switched off (the game is endless, for testing). The last commit
before the redesign (2f0335b) has an earlier v4 (hauling, adjacency bonuses, polyomino buildings,
walls, the shared stockpile); the later uncommitted v4 tuning was replaced by the redesign.

## Read this game to learn
- **A turn-order setup phase before simultaneous rounds** (`setup.py`): `Match.setup_order` is
  the whole `[(pid, piece)]` sequence and `setup_index` walks it; leaving drops the leaver's
  remaining pieces (`setup.drop`), and the last piece starts round 1.
- **Three simultaneous phases per round** (`Match.phase`: `place` -> `resolve` -> `plan`): `place`
  and `plan` end when every `Seat.ready` is set (`check_all_ready`; ready can be taken back until
  the last one); `resolve` ends when every `Seat.prompts` queue is empty
  (`resolution.check_done`).
- **Per-player prompt queues** (`resolution.py`): automatic jobs resolve at once, the rest
  become `{"type", "cell"}` entries in their owner's queue; `views.private` sends only the first
  one with its options (`ok` / `why` computed from the player's stock at that moment), and
  `answer` pops it. Every player answers their own queue at the same time.
- **Units as tile assignments** (`units.py`): `Match.assigned = {(x, y): {"pid", "soldier",
  "new"}}`, one per tile. `new` units (this place phase) can be taken back; stationed ones stay
  across rounds (Orders releases one). Free counts are derived (`units.free` = `seat.units` -
  placed), never stored. `units.job` says what a unit does on a tile; the same function feeds
  placement checks, the client's targets (`places`) and resolution (`job_here`).
- **Owned structures and reach** (`board.py`): every structure has an `owner`; `board.reach(pid,
  n)` is the square of radius n around the player's built buildings and roads, cached by
  `board.version`. Plans don't extend reach (so a plan is always reachable by its builders).
- **Costs with a non-resource currency**: royal decrees live on the seat (`Seat.decrees`, reset
  each planning phase from the buildings' `decrees`), but costs name them like a resource
  (`{"decrees": 1, "wood": 1}`); `Seat.pay` / `missing` handle both.
- **A two-half persistent market** (`market.py`): one `Market` per half, never redealt by the
  round; `Seat.reshuffled` tracks each player's once-per-round reshuffle of each half.
- **A gift form** (Trade): the client's Trade selection holds `to` and `give`; the server checks
  the shape (`playing.gift_reason`: 3 different x1 or 2 of one).

## Map
- `server.py`: the Map setting, `ACTIONS`, thin wrappers (`cell()`, `flag()`, `gift()`).
  `SYNC = PatchState`.
- `logic/match.py`: `Match` (constants: `HAND_SIZE`, `START_STOCK`, `COLORS`): `start_round`,
  `ready` / `check_all_ready`, `start_planning` (decrees), `end_round` (soldiers home, income,
  upkeep -> `units.starve`), guards `placing` / `planning`, `buy`, `reshuffle`, `leave`.
- `logic/setup.py`: `PIECES`, `KEEP_GAP`, `current`, `reason`, `spots`, `place`, `drop`.
- `logic/units.py`: `REACH`, `job` / `job_here`, `targets`, `place` / `unplace`, `free` /
  `free_soldiers`, `stationed`, `release`, `lose`, `starve`.
- `logic/resolution.py`: `resolve`, `options`, `title`, `answer`, `check_done`, `SCAVENGE`.
- `logic/playing.py`: `play` (build / action / curse), `build_spots`, `recall_spots`, `gift_reason`.
- `logic/views.py`: `public` (catalog cached on the match), `private` (hand, `places`, `setup`,
  `targets`, `prompt`, `reshuffled`).
- `logic/board.py`, `logic/seat.py`, `logic/market.py`, `logic/structures.py`, `logic/cards.py`,
  `logic/maps.py`: see `logic/__init__.py`.
- Dormant: `logic/foes.py`, `attacks.py`, `combat.py`, `enemies.py` and `content/enemies/` (plus
  the curse cards Fear, Hex, Frostbite, Ransom Note and the board's wall / blight / ruin helpers).
  Nothing in the running game calls them; they still expect the v4 shared stockpile
  (`match.stock`), `match.keep` and `match.soldiers`, so re-enabling enemies means rewiring them to
  per-player seats.
- `client/board.js` (`BastionBoard`: terrain, owner-coloured roads and buildings, greyed plans
  with 🔨n, unit badges), `client/panels.js` (status, details, prompt / Trade form, players with
  resource bars and Deck buttons, market halves, chronicle, card faces, deck window) and
  `client/game.js` (controller: hover outlines, clicks per phase, hand, Done); see their headers.
- `tests/test_lobby.py` (Sim: hidden hands, validation, setup turns, the phases, leaving).
  `tests/bots.py` and `tests/playtest.py` are the old v4 playtest harness, **disabled** (playtest
  exits at once); rewrite them for the new Match API before using them again.

## Pitfalls seen here
- The public state mixes the catalog and the board: the catalog's structure files are `kinds`,
  because `structures` is the board's buildings.
- PatchState: no `None` in dicts. Catalog views use `-1` for "no price" and `""` for "none";
  `setup` and `prompt` are `""` when there is none.
- Resolution runs inside `Match.ready` (and `Match.leave`); with no prompts it goes straight on to
  planning, so code after a ready may already find the plan phase.
- Free units are derived from `Match.assigned`; anything that removes a unit from the count
  (training, starving) must also clear its assignment (or pick a free one first, like `starve`).
- Soldiers on towers are cleared at the end of every round (`end_round`), workers on buildings
  never are.
- JSON turns tuple cell keys into strings: views send `"x,y"`; the client splits them.

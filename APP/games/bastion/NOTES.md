# Bastion: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files and their
fields: `content/README.md`. Tests: `tests/` (`python3 -I tools/run_tests.py bastion`).

## Read this game to learn
- **Co-op with simultaneous turns**: no `TurnQueue`; every seat has a `done` flag, any player
  acts at any time during a stage, and `Match.check_all_done()` advances (next build turn, siege,
  next level) once every remaining seat is done. A leave re-runs it, so a leaver never blocks.
  "Done" can be taken back (`done: false`) until the last player finishes.
- **A server-side simulation sent as a replay**: the siege (`logic/battle.py`) runs instantly
  and deterministically (no randomness, so tests are exact) and produces compact frames (one flat
  list `[uid, progress*100, hp, ...]` per tick) plus events (shots, keep hits, wall/squad health,
  breath, explosions). The client (`client/replay.js`) only interpolates and draws. With
  `SYNC = PatchState` the ~5-30 KB replay goes out once, not after every market purchase.
- **Server-computed targets**: `Match.private()` sends `targets` = {card id: {"x,y": labor}}
  for every placeable card in the hand (incl. the upgrade surcharge), so the client's hover ghost,
  target dots and "can't go here" need no placement rules. Board structures carry their effective
  stats (`damage`, `range` with forge/watchtower bonuses, barracks `rally`) for range circles.
- **Content-driven everything**: cards (a `kind` + per-level `stats`), enemies (abilities as
  optional objects), levels (waves) and maps (terrain + waypoint roads) are JSON; the host's Map
  setting is built from `MAPS`. Stats may be per level (`[3, 4, 6]`), read with `cards.stat()`.
- **Balancing with a bot**: numbers were tuned by a scratch greedy bot (not in the repo) playing
  full games through `Match` for 1-4 players and the three difficulties: roughly 85% wins on Easy,
  50% on Normal, 25% on Hard with the bot; knights (armor, level 5), rams (level 8) and the bosses
  (level 10) are the spikes. Enemy `hp` in the files is for 2 players; `PLAYER_SCALE` in
  `match.py` scales it (solo is gentler per hand, 3-4 players tougher).

## Map
- `server.py`: settings (difficulty, keep health, map from `MAPS`), `ACTIONS`, thin wrappers
  (`cell()` parses optional x/y), `check_over()` after every action. `SYNC = PatchState`.
- `logic/match.py`: `Match` (constants at the top: `HAND_SIZE`, `LABOR`, `START_GOLD`,
  `UPGRADE_LABOR`, `MIN_DECK`, `DIFFICULTY`, `PLAYER_SCALE`, seat `COLORS`): `start_turn`
  (refill, labor, farm/quarry income), `play` (structures via `Board`, orders via `orders.py`),
  `demolish`, `end_turn` / `ready` -> `check_all_done`, `siege` (runs `run_siege`, rewards,
  `bless` = chapels, deals the market), `buy`, `retire`, `next_level`, `leave`, `end`,
  `public` (static catalog cached in `catalog()`), `targets`, `private`.
- `logic/board.py`: `Structure` (uid, card, x, y, owner, level, hp), `Board` (`check` =
  placement rules, `place` (build or upgrade), `upgrade`, `demolish`, `disown`, `near`, `boost`,
  `rally`, `public`).
- `logic/battle.py`: `Siege` (one tick = `step`: spawn, towers, spikes, squads, enemy specials,
  walk/attack, keep), `Enemy`, `Tower`, `Wall`, `Squad`, `run_siege` -> `Result` (keep, replay,
  summary); removes destroyed walls from the board.
- `logic/orders.py`, `logic/seat.py`, `logic/market.py`, `logic/cards.py`, `logic/enemies.py`,
  `logic/maps.py`: see `logic/__init__.py`.
- `client/board.js` (`BastionBoard`): builds the grid (terrain, roads, bridges, unused roads
  dimmed, entrances, keep, structures with owner colour, ★ level, wall health).
- `client/replay.js` (`BastionReplay`): plays `game.battle` on `#overlay` (enemy sprites with
  health bars, squads, live walls, shot lines, blasts, keep hits, stunned towers), with pause,
  ×1/×2/×4 and Skip, then a result banner.
- `client/game.js`: status bar (level pips, stage, keep meter, "Watch siege"), board hover
  (ghost, target dots, range circles on `#ranges`, demolish mode), side panel (team, next siege
  with enemy tooltips, inspector, chronicle), bottom bar (hand or market), deck window (retire).
- `tests/`: `helpers.py` (fixture cards/enemies installed into the registries, a tiny map,
  `level`/`wave`, `give`, `build`, `siege`), `test_battle.py`, `test_rules.py`, `test_lobby.py`,
  `test_content.py` (loaders). Tests never check real card/enemy/level numbers.

## Pitfalls seen here
- First balance pass was far too easy: replaying the same structure card made level-3 towers
  before the first siege. Upgrades now cost +1 labor per current level (`UPGRADE_LABOR`); Master
  Mason stays a flat 1-labor upgrade.
- Enemies spawn on a road's first cell, so nothing may be built there (else a wall on it would
  never block anything).
- Blocking: an enemy stops `STOP` (0.55) cells before a blocker's cell and only blocks when it
  *reaches* that point, so a squad respawning on a cell an enemy already passed doesn't trap it.
- Replays must not auto-play right after a reload: game.js remembers the last battle id shown
  per room and game number in sessionStorage.
- The board is rebuilt on every state (cheap at 160 cells); hover highlights are toggled on the
  existing cells, and a running replay re-hides its walls on the new cells (`replay.attach`).
- `Match.public()` returns the cached catalog dicts; don't mutate the result.

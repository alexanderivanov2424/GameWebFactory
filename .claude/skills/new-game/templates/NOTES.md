# {{GAME_NAME}}: developer notes

Rules and the message list: the docstring at the top of `server.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py {{GAME_ID}}`).

## Read this game to learn
- TODO the patterns this game is a good example of (for whoever builds the next game).

## Map
- `server.py`: the lobby side: `SETTINGS`, `ACTIONS`, player options, and thin action methods
  that unpack each message and call `Match`. TODO timers, saved data.
- `logic/match.py`: `Match`, the rules and state of one game. TODO where the main rules are.
- `logic/`: TODO one line per extra module.
- `client/game.js`: TODO its render functions / sections.

## Pitfalls seen here
- TODO anything that bit you (and how it was solved).

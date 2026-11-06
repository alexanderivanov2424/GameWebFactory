# Color Tic-Tac-Toe: developer notes

Rules and the message list: the docstring at the top of `server.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py tictactoe`).

## Read this game to learn
The smallest complete game: the whole shape of a gamekit game in a few minutes.
- Host settings declared once in `SETTINGS`, including a linked bound
  (`winLength` can't exceed `boardSize`: `high="boardSize"`).
- A per-player lobby option with a uniqueness rule (`color` in `default_options` / `clean_options`).
- One game message (`place`) through `ACTIONS`, round-robin `TurnQueue` in a random order.
- Ending: a winning line, a full board (draw), or everyone else leaving (`on_player_removed`).

## Map
- `server.py`: `place()` validates and applies a move; `winning_line()` checks the four directions
  through the last piece.
- `client/game.js`: `renderLobby()` (player list with color dots, RGB inputs debounced into
  `setOptions`), `renderGame()` (rebuilds the board on every state).

## Pitfalls seen here
- Percentage heights inside a `<button>` don't resolve reliably (pieces came out oval):
  cells and pieces use explicit sizes from `--cell`.
- Don't overwrite the RGB inputs while the player is typing in any of them.

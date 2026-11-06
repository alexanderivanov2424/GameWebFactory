# Arena: developer notes

Rules and the message list: the docstring at the top of `server.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py arena`).

## Read this game to learn
- The smallest `RealtimeGame`: validated `on_input` (keys held), `tick(dt)` movement, public
  state of dicts keyed by public id with positions quantized to 0.1 and no None values.
- Client: `AppRealtime.attach`, `rt.controls`, `rt.sample` and `AppRealtime.loop` drawing a canvas.

## Map
- `server.py`: constants, `start_game` (ellipse placement), `on_input`, `tick`, `game_state`.
- `client/game.js`: `render*` build the DOM on lobby state; the `AppRealtime.loop` callback draws.

## Pitfalls seen here
- Pass an empty `onSnapshot` so per-tick snapshots don't re-render the DOM.
- A dot's "ping" key is left out (not None) until the server has a ping for that player.

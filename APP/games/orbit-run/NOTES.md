# Orbit Run: developer notes

Rules and the message list: the docstring at the top of `server.py`.
Tests: `tests/` (`python3 -I tools/run_tests.py orbit-run`).

## Read this game to learn
- A co-op trick-taking game: hands in `private_state` with the server sending which cards are
  `playable`, so the client holds no follow-suit rule.
- A **run** saved across games with `load_data` / `save_data` (logic/ship.py's `Run`): saved when a
  run starts and after every mission, to whoever was host at the start; the `run` setting
  (`Choice`) picks new or continue, `start_check` refuses "continue" without a continuable save.
- `lobby_game_state()` (gamekit hook): the host's saved run shown in the lobby as `state.game`.
- Content as JSON: `missions/` (mission cards, each in deck 1-3) and `tasks/` (a goal kind +
  success/failure effects); goal kinds are functions in `logic/tasks.py`'s `GOALS`.
- A drafting stage inside `playing` (`logic/draft.py`), a timed pause showing a full trick
  (`TRICK_PAUSE` in server.py, stage `collect`), then a `debrief` stage the host moves on from.

## Map
- `server.py`: settings (`run`), ACTIONS (`take`, `pass`, `play`, `next`), saving the run
  (`save_run`), the trick pause (`collect`), leaving ends the game.
- `logic/match.py`: `start_mission` (draw, upkeep, deal, captain, draft), `play` / `collect`
  (tricks), `task_status` (live done/failed/open), `end_mission` (effects, run over).
- `logic/cards.py`, `draft.py`, `tasks.py`, `missions.py`, `ship.py`: see `logic/__init__.py`.
- `client/game.js`: `renderMission` + `renderShip` (left), `renderTable` (seats placed on a
  circle with you at the bottom, played cards between the seat and the centre), `renderStatus`
  (draft buttons, debrief + Next mission), `renderPlayers` + log (right), `renderHand` (fixed bar).

## Pitfalls seen here
- With 3 players the hands are 14/13/13: a trick only includes players who still have cards, and a
  leader without cards hands the lead clockwise, so the last trick can be a single card.
- A task's "failed" while playing is only certain once it can't be won any more: `chances` counts
  the holder's cards left plus the current trick if they've already played into it.
- Mission decks: a played mission is discarded (`run.completed`); with every deck empty the run is
  "complete", so with one mission every finished run ends after it.

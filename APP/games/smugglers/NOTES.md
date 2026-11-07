# Smugglers: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files (boards,
goods, ship tiles, Interpol cards) and their fields: `content/README.md`.
Tests: `tests/` (`python3 -I tools/run_tests.py smugglers`).

## Read this game to learn
- **A graph board with swappable maps**: planets and dots as nodes, routes with lengths,
  routes branching off other routes' dots (`logic/board.py`), drawn as SVG (`client/board.js`,
  `AppDom.svg`). Reachability with blocking and stopping nodes (`Board.reach`).
- **Asymmetric roles**: one random Interpol vs. smugglers, different actions, hands and UI.
- **Deck-building** (Dominion style) with `gamekit.Deck`: hand/played/discard, market supply,
  cards that give pieces on the board, a card that repeats another (`logic/interpol.py`).
- **An interrupt inside a turn**: an inspection hands the action to another player (bribe,
  then decide) without moving the turn: `Match.actor()` vs `Match.turn()`.
- **A multi-step action**: pick up draws cards, then a separate `load` message finishes it
  (`m.loading` blocks everything else meanwhile).
- **PatchState** (first game to use it): the board is big and static, so only changes travel.
- The server sends rule answers to the client (`private.reach` per ship, `private.targets`
  per Interpol card and piece), so the client has no movement or placement rules.

## Map
- `server.py`: `SETTINGS`, `ACTIONS` and thin `on_*` wrappers that type-check messages
  (`text_field`, `uid_list`) and call `Match`; `on_game_message` checks `match.actor()`.
- `logic/match.py`: `Match` (setup, `_require_turn`, `end_turn`, `after_smuggler_action`
  auto-ends a turn when no ship can do anything, `remove`, `end`/scoring, `public`, `private`).
- `logic/smuggling.py`: `move`, `pickup`, `load`, `deliver`, `payout`, `reach`, `pickups`.
- `logic/interpol.py`: `Interpol` (deck, `play` -> `_check_piece` validates before changing
  anything, `buy`, `allowed` = where a piece may go, `private` = hand + targets).
- `logic/inspection.py`: `check` (queues an inspection for each loaded ship on a patrol's or
  checkpoint's spot; called after a move, a load and a patrol/checkpoint play) ->
  `next_inspection` -> `start`, then `bribe`, `decide`, `cancel`.
- `logic/board.py`, `logic/content.py`: loaders (+ contract generation).
- `client/board.js`: `SmugglersBoard.create(...)`: `draw(game, you)` rebuilds the SVG when the
  state changes; `highlight(...)` only toggles classes (reach, targets, selection).
- `client/game.js`: `renderGame()` calls `renderStatus`, `renderPrompt` (inspection, loading,
  Interpol targeting), `renderContracts` (tiles above the map; clicking a glowing one picks
  it up with the selected or only eligible ship), `renderPeople` (side scoreboard: cards,
  score, round), `renderPlayerBoards` (below the map in `turnOrder`, so the current player is
  first: ship tiles with a cargo slot and a vertical card stack; Interpol's play area and
  market), `renderLog`, `renderHand` (fixed bottom bar). Modes: `selectedShip`,
  `targeting` (repeat copy -> piece -> spot), `loadMarks`; `resetModes()` drops
  any that no longer apply.
- `tests/test_content.py` (board + files), `tests/test_rules.py` (Match), `tests/test_lobby.py` (Sim).

## Pitfalls seen here
- PatchState: never put `None` in the state (a null in a patch deletes the key). Optional
  fields are left out (`ship["contract"]`, `inspection`, `loading`, `turn` once over), and
  the client tests them as missing. The log is a dict keyed by index (`log["12"]`) plus
  `logSize`, so each patch adds one entry instead of resending the list.
- Barriers could seal off a planet or a ship: `Interpol.allowed` only offers dots that keep
  every planet and ship connected.
- Only ships carrying cargo stop at patrols or checkpoints or can be inspected
  (cargo count is public, so this leaks nothing). The rule is "a loaded ship on a spot with
  Interpol presence is inspected", so every way of getting there calls `inspection.check`:
  flying in, loading cargo there, and Interpol moving/placing a patrol or checkpoint onto it.
- With a fixed contract count, 2-player games ran past the round limit; contracts are per
  smuggler (`contractsEach`) so games last about as long at any player count (a bot run gave
  ~15 rounds at 2 players, ~27 at 6, where five face-up contracts are the bottleneck).
- Planet discs must stay distinct colors: contracts show the planets by their art.

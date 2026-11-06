# Peruvian Silver: developer notes

Rules and the message list: the docstring at the top of `server.py`. Card files and their
fields: `cards/README.md`.
Tests: `tests/` (`python3 -I tools/run_tests.py peruvian-silver`).

## Read this game to learn
The biggest game (server ~1300 lines, client ~1300), and the pattern book for anything with
simultaneous secret choices:
- **Stages inside `playing`**: `self.stage` is one of the constants near the top of
  `server.py` (choosing, reveal, charm, saved, fountain, fork, forked, robbery, auction,
  gem, marking, over). Each stage has a `SecretChoices` (or, for the auction, a turn
  pointer), a `decide_*`/`place_bid`/... method that validates one message, and a
  `finish_*` that applies the result and moves on.
- **Secret simultaneous plays**: `SecretChoices` (required choosers plus optional ones, e.g.
  players at camp holding Seconds, whom nobody waits for). The server sends only "chosen";
  `private_state` returns your own pick; `reveal()` shows all.
- **Timed pauses**: `self.schedule(delay, callback)` after a reveal, a saved strike or a fork
  pick. Callbacks start with a guard (`if self.phase != PLAYING or self.stage != ...`).
- **Resolve queue**: revealing a card queues path entries; `continue_resolving()` pops them
  and `resolve()` returns `NEXT`, `WAIT` (a decision stage was opened; the stage's `finish_*`
  calls `continue_resolving()` again) or `ENDED` (the expedition is over, drop the queue). A
  Mirror is just a second queue entry that resolves as the copied card.
- **Cards as JSON**: one file per card (`cards/deck/`, `cards/hand/`), plus id-to-count files
  for the starting deck and the Red Gem pool. `cards.py` loads and validates them at import
  with `gamekit.data`; bad files are logged and skipped. The client renders any card from
  `game.deckCards` / `game.handCards`, so text changes need no code. New behavior per card
  `type` goes in one place in the server (see "Adding a new kind of card" in `cards/README.md`).
- **Branching state**: per-player position (`seat["path"]`) and per-branch state
  (`self.paths`) exist even with one branch. Forking closes a path and opens two children;
  everything that used to assume "the path" takes a path id.
- **Per-copy card instances**: deck cards are `{"uid", "card", "marks"}` from the start, so
  marks (and removing exactly the copy that struck or was taken) work per physical card.
- **Hidden information**: hands, your marks, Crystal Ball visions, gem options and mark offers
  are in `private_state`; everything public is in `game_state`.

## Map
- `cards.py`: the loaders (`load_hand_cards`, `load_deck_cards`, `load_counts`,
  `load_marks`; they take a folder/file so tests can feed temp files) and the loaded
  constants `HAND_CARDS`, `DECK_CARDS`, `STARTING_DECK`, `POOL`, `MARKS`.
- `server.py`: `SETTINGS` and `ACTIONS` (thin `on_<action>` wrappers unpack the message and
  call the rule methods `play_card`, `decide_charm`, `place_bid`, ...). Deck card effects:
  `resolve()`. Hand card effects: `reveal()` (flee, then leave/backstab, then returns) and
  `play_card()` (validation). Between expeditions: `end_expedition` -> `begin_gems` ->
  `begin_marking` -> `begin_expedition`. Leaving mid-game: `on_player_removed` has one branch
  per stage (it must finish whatever the leaver was holding up). Scoring: `finish_game`.
- `client/game.js`: `render()` -> `renderGame()` calls one `render*` per area (seats, path,
  banner, log, hand, and one prompt per stage: charm, fountain, rob, auction, gem, draft).
  `canPlay`/`cardPlayable` decide what the hand bar allows; `firstTime(set, key)` gates every
  animation. The log text for each log entry type is built in `renderLog` and its helpers.
- `tests/test_cards.py`: loaders and the real card files. `tests/test_game.py`: rigged-deck
  rules tests (`rig(sim, [...])` sets the draw order; `step(sim)` runs one timer).

## Pitfalls seen here
- Don't copy rule tables into the client (which cards an explorer may play): send them in the
  state (`game.explorerPlays`). A hand-copied list once left Backstab unplayable.
- Animations only for what's new: rendering rebuilds the DOM, so remember what was already
  shown, keyed by `state.gameNumber` plus a server step counter (`game.step`, entry `step`),
  and never animate on the first render after a reload (`firstGameRender`). For a flip,
  insert the face-down element and add the flipped class in a double `requestAnimationFrame`.
- Keep the server's secret details out of public log entries (a Red Gem logs how many cards
  were added, not which).
- `theme.js` styles `.card` like `.panel`; this game's own `.card` (a playing card) resets
  `margin`, and sets its own border, padding, background and radius.
- The fixed hand bar needs bottom padding on `main` (`.with-hand`) and ~100px of right
  padding so PLAY stays clear of the chat tab.
- A new deck card `back` needs a `.back-<name>` style in `client/index.html`.
- Sim timers: `sim.run_timers()` also runs the timers those callbacks queue, so an expedition
  that ends rolls on into gems and marking. Run one at a time to look at the "over" stage.
- Expedition start resets `backpack`, `status` and `path` of every seat: set them after
  `begin_expedition`, not before.

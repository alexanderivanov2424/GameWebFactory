# Marooned: developer notes

Rules and the message list: the docstring at the top of `server.py`. Content files and their
fields: `content/README.md`. Tests: `tests/` (`python3 -I tools/run_tests.py marooned`).

## Design rule (from the user)
Every hidden mechanic must work the way it would in a physical board game: hidden cards,
choosing which card to reveal, a die only you see, talking, voting, attacking. The Imposter
gets **no special actions**; their power is the choices everyone has (announcing a worse
gather roll, discarding/revealing the bad build-check card, placing the worse explored tile,
lying in chat). The game never hands out clues either. Nobody is ever barred from anywhere:
the nightly vote changes no rules, and players deal with suspects by attacking them or not
helping them. Keep new features to this rule.

## Read this game to learn
- **A hidden role** (`match.imposter`): only `private.role` says it; the public state never
  does, until `result.imposter` at the end.
- **"Physical" hidden picks**: the secret gather roll (`actions.gather` stores the die in
  `match.pending`; `report(face)` accepts any face from 1 up to the roll) and the build-check
  hand-off (`checks.py`: the builder picks a helper before seeing cards, draws 3, discards 1;
  the helper reveals 1 of 2). Discards are never shown; the deck make-up and what's been
  revealed since the last shuffle are (`checkDeck`).
- **Map built as it's explored**: `Island` deals 2 tile cards, the explorer places 1 and steps
  onto it, the other goes under the deck.
- **A secret vote with only the tally shown**: `SecretChoices` read with `peek()` (never
  `reveal()`, which would publish ballots in `public()`); ballots are kept per player for
  end scoring.
- **Stats -> scoring and objectives**: `Survivor.stats` collects what happened (explored,
  built, lies, attacks, nights in the shelter...); `scoring.final` and the objective checks
  (`objectives.CHECKS`, keyed from JSON) read only those, so a new objective is usually just a file.
- **Waiting on someone other than the turn player**: `Match.actor()` (pending roll/tile, then
  the build-check step's player) vs `Match.turn()`; actions start only through `_require_free`.

## Map
- `server.py`: `SETTINGS`, `ACTIONS` -> thin `on_*` methods that type-check and call `Match`;
  `on_game_message` only checks the sender is still on the island, then `check_over()`.
- `logic/match.py`: stages and flow (`_start_day`, `end_turn` -> `_after_turn` -> vote ->
  `_after_votes` -> `night.sleep` -> next day or the monsoon; `_escape`), build checks
  (`choose_helper`, `discard_check`, `reveal_check`, `_resolve_check`), `remove`, `end`.
- `logic/view.py`: `public` / `private` (`moves` and `explorable` so the client has no
  movement rules).
- `logic/actions.py`, `logic/people.py`: one function per day action; constants (costs,
  `GATHER_YIELD`, `TOOL_BONUS`) at the top.
- `logic/camp.py` (projects, `SHELTER_LEVELS`, `RAFT_STAGES` scaled by player count),
  `checks.py`, `night.py`, `survivor.py` (`BASE_ENERGY`, `PACK_SIZE`, `TOOLS`),
  `objectives.py`, `scoring.py` (all point values), `island.py`, `content.py`.
- `client/board.js`: `MaroonedBoard` draws the grid (fog, tiles, tokens, move/explore targets).
- `client/prompts.js`: `MaroonedPrompts` draws the box above the board: objectives to keep,
  your secret roll, the tiles you drew, build-check steps, the night vote.
- `client/game.js`: status line, You panel (energy, backpack, tools, objectives, End turn),
  Square panel (resources, gather/search, pile, give/attack people here), Camp panel
  (projects, build, launch, check deck), players table, log, end-of-game scores.

## Balance (first pass, untested with people)
- Scratch bots (greedy, not in the repo) couldn't finish the raft in 12-16 days, but they
  wasted most of their energy wandering, carried materials around for days and crafted
  every tool. The numbers were eased after that: gather yields 0/1/1/2/2/3, cheaper shelter
  and raft, Swamp move 2, exploring steps you onto the square, crash supplies (1 Food per
  player), 6 stone per Hills, Sick only after 3 unsheltered nights, max energy never below 2,
  and the monsoon defaults to day 14. Tune after real games: costs are constants in `logic/`,
  tile and card counts are in `content/`.

## Pitfalls seen here
- Spend energy before drawing cards (explore, search), or a refused action would lose cards.
- Free actions (deposit, take, eat, give) can loop forever in bots; real players are fine.
- PatchState: optional keys (`turn`, `actor`, `check`, `pending`, `launchDay`, `voted`,
  `picked`) are left out, never `None`; the log is a dict keyed by index plus `logSize`.
- A player leaving mid-action: a half-done explore places the first card; a build check
  resolves with a random card from the current hand (`CheckDeck.pick_any`).

# Peruvian Silver cards

Everything here is read when the game server starts, so redeploy (`./deploy.sh`) after a
change. Mistakes are skipped and the reason is written to the server log
(`journalctl -u app-server`).

## `starting-deck.json`: the deck at the start of a game

Card id → number of copies (0–50). Ids are file names from `deck/`.

```json
{ "cave-in": 3, "small-pile": 1 }
```

The deck carries over between expeditions: a hazard that strikes loses one copy (the
one that struck), and a taken relic leaves it. Nothing is added during the game.

## `pool.json`: what a Red Gem can add

Card id → weight (0–1000): how likely it is to be one of the 5 cards a Red Gem offers.

## `marks.json`: the emoji players mark cards with

`{"emoji": ["🔺", "⭐", "🌙", "🍀", "💧"]}` (at least 3, all different). After each
expedition except the last, 3 of them are drawn at random, the same for everyone. Each
player is privately shown 3 different random cards from the deck (faces only, never
anyone's marks) and puts one of the 3 emoji on the back of one of them. Marks stay on that
card for the rest of the game. Everyone sees the marks on the back of the top card of the
deck, and on cards once they're revealed. Only you know which marks you placed.

## `deck/`: deck card definitions, one file per card

The file name (without `.json`) is the card's id: lowercase letters, digits, `-` or `_`.
A card is only used if `starting-deck.json` or `pool.json` lists it.

| Field    | Required | Meaning |
|----------|----------|---------|
| `name`   | yes      | Shown on the card. |
| `type`   | yes      | `treasure`, `hazard`, `charm`, `idol`, `relic`, `mirror`, `gremlin`, `fountain`, `pot`, `fork`, `altar`, `blessing`, `death`, `robbery` or `gem`. |
| `icon`   | no       | An emoji shown on the card. |
| `text`   | no       | Flavor or rules text: shown on hover, in the draft picker and in the log. |
| `value`  | treasure, idol | Treasure: silver split evenly between everyone still exploring; the remainder stays on the card. Idol: points added to the holder's score at the end of the game. |
| `protects` | charm  | Id of the hazard card this charm protects against. |
| `gives`  | relic    | Id of the card in `hand/` that taking this relic puts in your hand (Flee, Stash, Guide Dog, Seconds). |
| `color`  | gem      | `red` or `blue`. |
| `growth` | pot      | Silver added to it every turn after it's revealed (default 5). |
| `blackSquare` | no  | `true`: its back shows a black square (separate from player marks). Death and Blessing have it. |
| `back`   | no       | Which card back it has (default `default`). Players see the back of the top card of the deck. A new back needs a `.back-<name>` style in `client/index.html`. |

What each type does:
- `treasure`: split between everyone exploring that path (plus one share per Gremlin); remainder stays on the card.
- `hazard`: see below.
- `charm`, `idol`, `relic`: relics, see below.
- `mirror`: becomes a copy of the next card revealed on its path and resolves as that card (a Mirror then a hazard is an instant pair).
- `gremlin`: takes a share of every treasure split on its path after it; its share stays on it for leavers.
- `fountain`: the fountain pool of every player still exploring (any path) doubles; players at camp or knocked out don't double, then everyone exploring that path secretly moves silver between backpack and pool. Pools last all game but only count once taken back out.
- `pot`: starts at 0 and gains `growth` every turn; leavers share it like any leftover.
- `fork`: after the decision that follows it, its path closes (every card but the Fork and
  hazards is discarded; silver on them is lost; untaken relics stay in the deck) and two
  cards start a left and a right path. Everyone on the forked path then picks a side
  (Stay = left, Leave = right), and each new path's first card resolves for its players.
  A waiting Mirror never copies a Fork; the split discards it.
- `altar`: everyone exploring its path puts their whole backpack on it; leavers split it.
- `blessing`: everyone exploring (any path) doubles their backpack.
- `death`: unavoidable (no charm or Guide Dog): everyone exploring loses their backpack and
  the expedition ends. It stays in the deck.
- `gem`: auctioned when revealed. Every player bids once from their chest, in seat order
  (the first bidder rotates); a bid must beat the highest so far, 0 passes. Only the winner
  pays (the silver is gone). Nobody bids: it stays in the deck. At the end of the round a
  `red` gem lets its holder add 3 of 5 cards from `pool.json` to the deck (secretly); a
  `blue` gem puts a mark of their choice on 3 random deck cards (they see which). Gems
  won in the last round do nothing.
- `robbery`: the player(s) with the most silver in their chest each choose one relic they
  hold (charm, idol or relic card) to lose. Ties: everyone tied loses one.

Card borders show the category: treasure, hazard (hazards and Death), idol (charms, idols
and relics: anything a lone leaver picks up) and event (everything else).

At the end of the game, idols score their `value`, and every other unused relic (charms
and relic cards still in hand) scores 5.

Hazards: when a second (or third...) card with the **same id** is revealed in one
expedition, it strikes: one copy leaves the deck, and everyone still exploring loses their
backpack unless they spend a matching charm.

Treasures are named by the size of the pile (Pinch, Handful, Pile, Heap, Mound, Hoard...),
not by objects.

Charms, idols and relics: stay on their card in the mine. A player who leaves alone (the only leaver that
turn, or the only one left when the deck runs out) takes every relic on the path into
their hand. A taken relic leaves the deck. Who holds which relic is public. Idols are
worth their `value` at the end of the game (score = chest + idols). When its
hazard strikes, the holder secretly decides whether to spend it to keep their backpack
and keep exploring. Charms can also go in `pool.json`.

## `hand/`: cards players hold and play in secret

| Field      | Required | Meaning |
|------------|----------|---------|
| `name`     | yes      | Shown on the card. |
| `type`     | yes      | `stay`, `leave`, `flee`, `stash`, `guard` or `return`. |
| `starting` | no       | How many copies each player starts with (default 0). |
| `order`    | no       | Position in the hand, lowest first (default 100). |
| `reusable` | no       | `true`: goes back to the hand after it's revealed. Otherwise it's used up. |
| `icon`     | no       | An emoji shown on the card. |
| `text`     | no       | Rules text shown on hover. |

Hand card types: `stay` (keep exploring), `leave` (go to camp), `flee` (leave before the
Leave players, collecting first), `backstab` (leave, and rob everyone on your path who
plays Leave that turn: their backpacks and leftover shares are split evenly between the
back-stabbers; fleers escape), `stash` (bank your backpack and keep exploring), `guard`
(Guide Dog: stay, but if the next card makes a hazard strike, go home with your backpack),
`return` (Seconds: played from camp while others are still exploring; go back in),
`peek` (Crystal Ball: used any time, not as a turn; shows only you the next 3 cards).
Card `text` should stay short (one line): it shows on hover and in the marking view.

## Paths

Every expedition starts on the main path: the row where cards are revealed. Forks split a
path into left and right paths (and those can fork again). Each turn every open path with
explorers gets a card. Treasure is shared, and leftovers are collected, only within a path.
Hazards count across all paths and strike everyone. Seconds lets you pick which path to rejoin.

## Adding a new kind of card

A new `type` needs code in `../cards.py` and `../server.py`: add it to `DECK_TYPES` or
`HAND_TYPES` (and its fields to the parser) in `cards.py`, and handle it where cards are
resolved in `server.py` (`resolve` for deck cards, `reveal` and `play_card` for hand
cards). The client shows any card from its name, icon, value and text. `cards.py` loads and
validates all the files here; `../tests/test_cards.py` checks them.

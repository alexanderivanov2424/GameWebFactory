# Bastion 2 content files

One JSON file per item; the file name (lowercase letters, digits, `-`, `_`) is its id. Bad files
are logged and skipped (logger "bastion2"); references to unknown cards are dropped with a log
line. Loader and card text: `logic/content.py`. Card and structure ids share one namespace (a
structure is also the card you build it with).

Costs (`cost`, `pay`) may name temporary resources, `food` and `population` (available
population this turn). Gains (`gain`) may name temporary resources and `food`.

## resources.json
`{id: {"name", "icon", "temporary": true}}`. Temporary resources (wood, stone, wheat) are play-area
counters, cleared at the end of every turn. `food` and `population` are permanent and always
exist (food is capped by food storage; population is spent per turn by builds).

## starting-deck.json
`{"deck": {card id: copies}, "after_first_hand": {card id: copies}}`: the first hand is dealt
from `deck`, then `after_first_hand` (2 Villagers) is shuffled into the draw pile.

## cards/<id>.json
- `name`, `icon`, `kind`: `"resource"`, `"upkeep"` or `"action"` (default), optional `text`
  (generated from the fields otherwise), `market`: `"always"` / `"shop"` (+ `copies` in the
  shop deck) to sell it; leave out to never sell it.
- resource: `resource` (a temporary resource or `food`), `value` (default 1). Bundling looks up
  the resource card with the same `resource` and the bundled total as `value`.
- upkeep: `pay` {cost} (one way to play it), `discard` n (the other: discard n other cards; 0 =
  not allowed), `paid_off: true` (leaves the deck once played), `discarded`: what happens when it
  leaves the hand unplayed: `add` (a card id into the discard pile), `population` (negative:
  lose that many, each with a Villager card), `remove: true` (the card leaves the deck).
- action: an effect (below); `actions` is what it costs to play.

## structures/<id>.json
- `name`, `icon`, optional `text`, `cost` {cost} to build it (next to one of your built
  structures; built at the end of the turn), `market` / `copies` as for cards (the castle has none:
  it's only placed at setup). Buying a structure from the market pays its cost (plus the buy
  action) and places it at once; it never becomes a card. A structure can still be a hand card
  (e.g. in starting-deck.json): playing it pays the cost and places it the same way.
- `provides`: `{"food_cap": n, "actions": n}` while it stands (the castle: 5 food, 1 action).
- `on_build`: `{"population": n, "add": [{"card", "count"?, "optional"?}]}` once, when built
  (cards go to the discard pile; `optional` ones can be unticked in the play area).
- `action`: an effect usable once per turn (listed on the left of the screen).

## Effects (action cards and structure actions)
`{"name", "actions": n (action points; 0 = free; default 1), "pay": {cost}, "gain": {gain},
"card": id (a temporary copy into your hand: gone once played or discarded), "draw": n,
"bundle": [values]}`. `pay` + `gain` is a conversion (temporary -> temporary, temporary -> food,
food -> temporary...). `bundle`: pick resource cards of one kind adding up to one of the values
and trade them for that kind's card of that value (the picked cards leave the deck).

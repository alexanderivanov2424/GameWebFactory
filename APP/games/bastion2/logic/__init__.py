"""Bastion 2: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py     Match: one game's flow (setup: castle, house, farm; then turns, together or one at
                 a time), buying, ending a turn (builds complete, discard, draw), leaving.
    effects.py   What cards and structures do: playing resource / action / upkeep / structure
                 cards, pending builds (take back, optional cards), structure actions (bundling),
                 discard penalties, losing population, completing builds.
    board.py     Board: the unbounded grid of one-tile structures, its shown bounds, build spots
                 (next to your built structures) and castle spots.
    seat.py      Seat: one player's deck, hand, play area, temporary and permanent resources,
                 actions, used structures and pending builds.
    market.py    Market: always-for-sale cards and the shop row dealt from the shop deck.
    content.py   Loading content/ (resources, cards, structures, starting deck) and card text.
    views.py     What clients see: public state (with the cached catalog) and private state
                 (hand with why each card can't be played, spots, structure actions, pending builds).

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It may import
gamekit, never `server`. Import sibling modules relatively.
"""

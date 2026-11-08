"""Gilded Trail: the game's rules, kept apart from the lobby (server.py).

Modules (keep this list and NOTES.md's map up to date as you add more):
    match.py     Match: one game's state, turn flow, game end and ranking, public/private state.
    content.py   Loaders for cards/*.json and maps/*.json (CARDS, MAPS).
    board.py     Hex geometry and the procedural board (tiles, terrain, starts, goals, blockades).
    market.py    Market: the 6 slots, the reserve and the supply.
    movement.py  Moving explorers with cards, rubble/base camps, blockades, the golden city,
                 and the legal steps sent to the client (options, guide_targets).
    actions.py   Buying and action cards (draw, remove, free card, Local Guide).

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It imports only
gamekit, never `server`.
"""

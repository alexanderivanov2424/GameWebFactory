"""Smugglers: the game's rules, kept apart from the lobby (server.py).

Modules (keep this list and NOTES.md's map up to date as you add more):
    match.py       Match: setup, roles, turn flow (smugglers then Interpol), who acts now,
                   end of game and scoring, public()/private() state. Calls the others.
    board.py       Board: loads content/boards/*.json (planets, routes, dots), geometry
                   (neighbours, reach with barriers/checkpoint stops, distance, connected).
    content.py     Loaders for content/goods, content/ships, content/interpol; contract generation.
    smuggling.py   Smuggler ship actions: move, pick up + load, deliver, payout.
    interpol.py    Interpol: deck-building (gamekit.Deck), playing/buying cards, card effects,
                   pieces on the board (barriers, checkpoints, patrols) and where they may go.
    inspection.py  Inspections (a loaded ship on a patrol's or checkpoint's spot), queued one
                   at a time: bribe, then inspect or let pass; seizures and fines.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests drive it directly (see tests/). It imports gamekit only.
"""

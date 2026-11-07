"""Block Blast: the game's rules, kept apart from the lobby (server.py).

Modules (keep this list and NOTES.md's map up to date as you add more):
    match.py    Match: one game's state and turn flow (place, patch, buy, aim, end turn,
                clears and damage, knock-outs, leaving), public()/private(pid).
    tiles.py    Tile types (blue, grey, goblin) and their behaviour flags (spoils, unspoilable).
    symbols.py  Symbols (coin, attack, shield, chapel, siege) and their codes.
    effects.py  What a clear does: spoiled lines (by tile type), one effect function per symbol,
                the attack (strength, shields), knock-outs.
    board.py    A 9x9 board of (tile, symbol) cells and piece geometry: fits, place, full
                rows/columns, clearing, the two-layer form clients get.
    bank.py     Bank: the 5 face-up bonus cards, prices by slot, refill at the end of a turn.
    cards.py    Loading cards/ (tiles + symbols layers, flags, deck counts) and precomputing
                the 4 rotations of each card's piece.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests drive it directly (see tests/). It imports gamekit
(Deck, TurnQueue, LobbyError, gamekit.data), never `server`.
"""

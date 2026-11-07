"""Block Blast: the game's rules, kept apart from the lobby (server.py).

Modules (keep this list and NOTES.md's map up to date as you add more):
    match.py    Match: one game's state and turn flow (who may act when, place, patch, buy, aim,
                card removal, end turn, running clears, knock-outs, leaving), public()/private(pid).
    seat.py     Seat: one player's board, resources, deck and hand; its public/private view.
    effects.py  What a clear does: which lines clear and which are spoiled (by tile type), one
                effect function per symbol, damage against shields. Pure: no log, no Match.
    board.py    A 9x9 board of (tile, symbol) cells and piece geometry: fits, place, full
                rows/columns, clearing, the two-layer form clients get.
    tiles.py    Tile types (blue, grey, goblin) and their behaviour flags (spoils, unspoilable).
    symbols.py  Symbols (coin, attack, shield, chapel, siege, the decorative goblin face).
    bank.py     Bank: the 5 face-up bonus cards, prices by slot, refill at the end of a turn.
    cards.py    Loading cards/ (tiles + symbols layers, flags, deck counts) and precomputing
                the 4 rotations of each card's piece.

Imports go one way: match -> seat, bank, cards -> effects -> board -> tiles, symbols (cards
uses effects only to leave art-only symbols out of its counts).

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests drive it directly (see tests/). It imports gamekit (Deck,
TurnQueue, LobbyError, gamekit.data), never `server`.
"""

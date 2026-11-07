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
    market/     The market (shared pool of bonus cards) and its types, one module each:
                base.py (Market), conveyor.py (ConveyorMarket), cost.py (CostMarket); the
                registry MARKETS in market/__init__.py drives the lobby settings.
    cards.py    Loading cards/shapes/ (tiles + symbols layers, flags, cost) and the starting
                deck, precomputing the 4 rotations of each card's piece.
    packs.py    Card packs (cards/packs/): the sets of bonus cards the host picks for the
                market's pool.

Imports go one way: match -> seat, market, packs -> cards -> effects -> board -> tiles, symbols (cards
uses effects only to leave art-only symbols out of its counts).

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests drive it directly (see tests/). It imports gamekit (Deck,
TurnQueue, LobbyError, gamekit.data), never `server`.
"""

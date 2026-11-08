"""Bastion: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py    Match: one game's flow (build turns -> siege -> market -> next level), playing
                cards, demolishing, buying/retiring, leaving, what clients see (incl. targets).
    board.py    Board + Structure: the map plus structures, placement/upgrade rules, adjacency
                bonuses (boost), barracks rally cells.
    battle.py   run_siege: the deterministic tick-by-tick siege and its replay for the client.
    orders.py   apply_order / check_target: what order cards do.
    seat.py     Seat: one player's deck, hand, labor, gold and done flag.
    market.py   Market: the shared offer between levels (unlimited copies), retire cost.
    cards.py    CARDS / STARTING_DECK loaders (content/cards/, content/starting-deck.json), stat().
    enemies.py  ENEMIES / LEVELS loaders (content/enemies/, content/levels/), public_level().
    maps.py     MAPS loader (content/maps/): terrain, keep, roads expanded to cells.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It may import
gamekit, never `server`. Import sibling modules relatively.
"""

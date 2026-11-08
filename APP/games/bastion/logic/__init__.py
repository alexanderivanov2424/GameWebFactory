"""Bastion: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py       Match: one game's flow (rounds, end of round, arrivals, win/loss), playing
                   cards (build, actions, curses), striking and razing enemies, buying, leaving.
    views.py       What clients see: public state (with the cached catalog), private hand and
                   where each hand card may go (targets).
    board.py       Board + Structure: terrain and everything placed, placement rules, "next to"
                   counts, links to depots (roads), raid protection, ruin/repair, blights.
    economy.py     Building output (base + adjacency bonuses - blight), whether a building can
                   work, working it (goods to the stockpile or stored), hauling, repair cost.
    attacks.py     What an enemy attack does (steal, ruin, keep damage, blights, curses,
                   plague, freeze, kill soldiers).
    foes.py        The enemies of one game: lineup, health scaling, arrival (lairs), damage.
    seat.py        Seat: one player's deck, hand and done flag.
    market.py      Market: the shared row of cards for sale (unlimited copies).
    structures.py  STRUCTURES loader (content/structures/), resources, terrain, condition text.
    cards.py       CARDS (content/cards/ + a blueprint and a crew card per structure) and
                   STARTING_DECK (content/starting-deck.json), card text.
    enemies.py     ENEMIES loader (content/enemies/), attack and defeat text.
    maps.py        MAPS loader (content/maps/): terrain rows and the starting town.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It may import
gamekit, never `server`. Import sibling modules relatively.
"""

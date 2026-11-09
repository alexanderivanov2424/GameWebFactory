"""Bastion: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py       Match: one game's flow (rounds, the place and act phases, turn order from a
                   rotating first player, end of round, arrivals, win/loss), buying, rerolling
                   the market, leaving; thin wrappers over the modules below.
    units.py       Units (worker placement): handing them out, targets ("s<uid>", "haul",
                   "fight<i>", "raze<x>,<y>"), placing / taking back, resolving (work, haul,
                   fight, raze), losing unresolved units, previews.
    food.py        Population (houses, the keep) and upkeep: bread and wheat eaten, hungry people.
    hauling.py     Haul capacity (Carriages make the first hauls bigger), haul sources, taking goods.
    playing.py     Playing a hand card: blueprints build, curses are paid off, actions (repair,
                   cure, gain, draw, adds, trash).
    combat.py      Soldier strikes, razing enemy tiles, units fighting (strikes carry over),
                   damage and beating enemies, cures.
    views.py       What clients see: public state (with the cached catalog), private hand, where
                   each hand card may go (targets), unit previews (places) and haul sources.
    board.py       Board + Structure: terrain and everything placed, placement rules, "next to"
                   counts, links to depots (roads), raid and loot protection, ruin/repair, blights.
    economy.py     Building output (base + adjacency bonuses - blight, +1 with a tool), whether a
                   unit may go on / work a building, working it (goods to the stockpile or
                   stored), repair cost.
    tiles.py       Road and wall tiles: placed from the team's stocks (bought in batches of 3),
                   removed for free.
    attacks.py     What an enemy attack does (steal, loot building stores, ruin, keep damage,
                   blights, curses, plague, freeze, kill soldiers).
    foes.py        The enemies of one game: lineup, health scaling, arrival (lairs), damage, strikes.
    seat.py        Seat: one player's deck, hand, units and ready flag.
    market.py      Market: the shared row of cards for sale (unlimited copies), dealt anew
                   each round or on a reroll.
    structures.py  STRUCTURES loader (content/structures/), resources, terrain, condition text.
    cards.py       CARDS (content/cards/ + a blueprint per structure with a price) and
                   STARTING_DECK (content/starting-deck.json), card text.
    enemies.py     ENEMIES loader (content/enemies/), attack and defeat text.
    maps.py        MAPS loader (content/maps/): terrain rows and the starting town.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/). It may import
gamekit, never `server`. Import sibling modules relatively.
"""

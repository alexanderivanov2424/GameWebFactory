"""Marooned: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py      Match: stages (objectives, day, vote, over), turns, nights and dawns, the
                  build-check flow, players leaving, the end; delegates everything else.
    view.py       public(m) / private(m, pid): what clients see.
    content.py    Loaders for content/ (tiles, finds, build-check cards) and the item list.
    island.py     Island: the grid, the tile deck (draw 2, place 1), tiles, resources, piles.
    survivor.py   Survivor: energy, hunger, health, backpack, tools, per-player stats; TOOLS.
    actions.py    Day actions out on the island: move, explore/place, gather/report, search.
    people.py     Day actions with items and people: deposit, take, build, craft, eat, heal,
                  give, attack, launch.
    camp.py       Camp and Project: the shelter levels and raft stages.
    checks.py     Build checks: helper first, then 3 cards -> discard 1 -> helper reveals 1.
    night.py      The secret vote (tally only), hunger and sleep.
    objectives.py Secret objectives: loading content/objectives and the check functions.
    scoring.py    Running points during play and the final breakdown.

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly (see tests/).
"""

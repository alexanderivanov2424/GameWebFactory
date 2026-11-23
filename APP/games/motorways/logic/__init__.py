"""Metro Lanes: the game's rules, kept apart from the lobby (server.py).

Modules:
    match.py     Match: one game in progress: players, week clock and weekly picks, tick order.
    grid.py      Grid: tiles, terrain from a seed (river, mountains), the area that grows weekly.
    roads.py     RoadNet: road tiles and links by owner, bridges/tunnels, roundabouts and
                 lights, erasing with refunds, buildings' driveways, routes (Dijkstra trees).
    city.py      City: houses and shops appearing, shop demand (pins), the overflow timer.
    traffic.py   Traffic: cars dispatched to pins, lanes, junction capacity, points per tile passed.
    players.py   Player: each player's stock of pieces, points and weekly pick.
    upgrades.py  The weekly delivery and the upgrade offers.
    view.py      What clients see (the contract with client/*.js).

Code here knows players only by public id ("p1", "p2", ...), never by Member objects, the
network or the lobby phase, so tests can drive it directly.
"""

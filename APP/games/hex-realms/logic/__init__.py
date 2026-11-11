"""Hex Realms rules (package games.hex-realms.logic). No lobby, network or Member code here.

Modules:
    match.py     Match: one game's state, turn resolution order, eliminations, score, public/private
    orders.py    the orders a player gives while planning (validation, paying, refunds)
    movement.py  paths (reach, path) and simultaneous step-by-step movement with collisions
    combat.py    dice battles, ranged shots, sieges of structures, tower fire
    economy.py   territory, workers, production, upkeep, growth
    logistics.py goods in stores, road networks (roads + navigable structures), spending, deliveries
    vision.py    fog of war: what each player sees, has explored and remembers; their map view
    bots.py      computer players: plan a turn through the same orders as people (fog applies)
    mapgen.py    the random hex map and fair starting spots
    content.py   loads structures/, units/, advances/ (JSON) and the terrain table
"""

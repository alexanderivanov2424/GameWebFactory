"""Hex Realms rules (package games.hex-realms.logic). No lobby, network or Member code here.

Modules:
    match.py     Match: one game's state, turn resolution order, eliminations, score, public/private
    orders.py    the orders a player gives while planning (validation, paying, refunds)
    movement.py  paths (reach, path) and simultaneous step-by-step movement with collisions
    combat.py    dice battles, ranged shots, sieges of structures, tower fire
    economy.py   territory, workers, production, upkeep, growth
    logistics.py goods in the realm's stores: stock, spending, refunds, filling
    construction.py  construction sites: build turns and builders (idle people), finishing structures
    explore.py   the Explore order: where a unit walks on its own to clear fog (bots scout with it)
    vision.py    fog of war: what each player sees, has explored and remembers; their map view
    bots.py      computer players: plan a turn through the same orders as people (fog applies)
    mapgen.py    the random hex map and fair starting spots
    content.py   loads structures/, units/, advances/ (JSON) and the terrain table
"""

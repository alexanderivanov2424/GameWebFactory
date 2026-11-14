"""Hex Realms rules (package games.hex-realms.logic). No lobby, network or Member code here.

Modules:
    match.py     Match: one game's state, turn resolution order, eliminations, score, public/private
    orders.py    the orders a player gives while planning (validation, paying, refunds)
    recruiting.py where recruits appear; structures that recruit on their own (with a standing order)
    movement.py  paths (reach, path) and simultaneous step-by-step movement with collisions
    combat.py    dice battles, ranged shots, sieges of structures, tower fire
    territory.py strong land (structures' reach) and weak land (bought with gold, easily lost)
    economy.py   workers, production, upkeep, growth
    logistics.py goods in the realm's stores: stock, spending, refunds, filling
    construction.py  construction sites: build turns and builders (idle people), finishing structures
    standing.py  standing orders kept across turns: Explore, Fight, Pillage, Travel (multi-turn moves)
    explore.py   where an exploring unit walks to clear fog (bots scout with it)
    vision.py    fog of war: what each player sees, has explored and remembers; their map view
    bots.py      computer players: plan a turn through the same orders as people (fog applies)
    mapgen.py    the random hex map and fair starting spots
    content.py   loads structures/, units/, advances/ (JSON) and the terrain table
"""

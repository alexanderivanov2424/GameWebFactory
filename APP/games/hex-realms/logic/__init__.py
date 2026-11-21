"""Hex Realms rules (package games.hex-realms.logic). No lobby or Member code here.

    match.py         Match: one game's state, turn resolution, eliminations, score
    orders.py        orders given while planning (validation, paying, refunds)
    recruiting.py    where recruits appear
    movement.py      paths and simultaneous step-by-step movement
    combat.py        dice battles, shots, sieges, tower fire
    territory.py     strong land (structures' reach) and bought weak land
    economy.py       workers, production, upkeep, feeding, new people
    logistics.py     goods in stores: stock, spending, refunds, filling
    construction.py  construction sites and finishing structures
    standing.py      standing orders across turns (Explore, Fight, Pillage, Travel)
    explore.py       where an exploring unit walks to clear fog
    vision.py        fog of war and each player's map view
    bots.py          computer players (they plan through the same orders)
    mapgen.py        random hex map and fair starting spots
    content.py       loads structures/, units/, advances/ (JSON) and terrain
"""

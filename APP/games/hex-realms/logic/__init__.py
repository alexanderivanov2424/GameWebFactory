"""Hex Realms rules (package games.hex-realms.logic). No lobby, network or Member code here.

Modules:
    match.py     Match: one game's state, turn resolution order, eliminations, score, public/private
    orders.py    the orders a player gives while planning (validation, paying, refunds)
    movement.py  paths (reach, path) and simultaneous step-by-step movement with collisions
    combat.py    dice battles, ranged shots, sieges of structures, tower fire
    economy.py   territory, road connections, workers, production, upkeep, growth
    mapgen.py    the random hex map and fair starting spots
    content.py   loads structures/, units/, advances/ (JSON) and the terrain table
"""

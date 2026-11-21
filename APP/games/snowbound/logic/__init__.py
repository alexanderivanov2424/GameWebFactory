"""Snowbound rules (package games.snowbound.logic). No lobby code: players are public ids.

Modules:
    match.py     Match: one game (players, world, weather, huts, golden snowflakes, finds, actions, goal)
    avatars.py   Player characters: walking with collision (mirrored in client/grid.js), shoveling
    world.py     World: the grid of lots (snow, reached, features, workable targets, row strings)
    economy.py   Player: wallet, machines, upgrades, supplies, needs, rates and click power
    units.py     Units: one worker per machine owned; targeting (rally points), moving, digging
    survival.py  Weather, stove/huts and the woodpile, food and warmth near heat, blizzard snowfall, deliveries
    content.py   Loads machines/*.json and upgrades/*.json (+ generated x2 tiers per machine), prices
    view.py      public/private state sent to clients
"""

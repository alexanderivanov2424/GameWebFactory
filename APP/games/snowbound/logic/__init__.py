"""Snowbound rules (package games.snowbound.logic). No lobby code: players are public ids.

Modules:
    match.py     Match: one game (players, world, weather, golden snowflakes, finds, actions, goal)
    world.py     World: the grid of lots (snow, reached, features, workable targets, row strings)
    economy.py   Player: wallet, machines, upgrades, supplies, needs, rates and click power
    crews.py     Machine crews: one vehicle per player and machine kind; targeting, driving, digging
    survival.py  Weather cycle, shared stove and woodpile, food/warmth, blizzard snowfall, deliveries
    content.py   Loads machines/*.json and upgrades/*.json (+ generated x2 tiers per machine), prices
    view.py      public/private state sent to clients
"""

"""Snowbound rules (package games.snowbound.logic). No lobby code: players are public ids.

Modules:
    match.py     Match: one game (players, world, weather, huts, golden snowflakes, finds, actions, goal)
    avatars.py   Player characters: walking with collision (mirrored in client/grid.js), shoveling
    world.py     World: the grid of lots (snow, reached, features, workable targets, row strings)
    economy.py   Player: wallet, machines, upgrades, supplies, needs, rates and click power
    units.py     Units: one per machine owned; shared targeting (rally points), moving, work() loop
    machines.py  What each machine kind does (tunnelling dogs, braziers, dozers, augers, jets...)
    uniques.py   The unique helpers landmarks give (mammoth, snow spirit, St. Bernard, golem, hot spring)
    hauling.py   Haulers carry dug snow to drop points (cabin, Snow Depots, rail stations, processors); trips, depots
    roads.py     Road levels and laying them; route fields over the road network (incremental, budgeted)
    factory.py   Processors (snow -> goods, chained side by side) and sleds selling goods at a market
    landmarks.py Hidden one-of-a-kind ruins: placement, rewards when fully cleared, team effects
    survival.py  Weather, stove/huts and the woodpile, food and warmth near heat, blizzard snowfall, deliveries
    content.py   Loads machines/, upgrades/, goods/ and landmarks/ (*.json), machine prices
    view.py      public/private state sent to clients
"""

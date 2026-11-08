"""Deep Colony rules (package games.deep-colony.logic). No lobby, network or Member code: players
are public ids ("p1"). Modules, one topic each:

    content.py    elements/*.json and buildings/*.json: loading, validation, fast index lists
    grid.py       World: the cell grid (element, mass, temperature, germs per cell; tile flags)
    mapgen.py     generate(w, h, rng): a seeded map with the start room and Arrival Pod spot
    fluids.py     gas and liquid movement
    heat.py       heat conduction and phase changes (freezing, melting, boiling, condensing)
    germs.py      germ die-off, off-gassing, and the decor field
    buildings.py  Building (sites and finished buildings), placement rules, cell layers
    items.py      loose debris piles
    networks.py   power (wires); liquid and gas pipes, packet by packet per segment
    machines.py   behaviour of each building kind (power, oxygen, food, plumbing, heat...)
    nav.py        where colonists can walk/climb, distance maps, paths
    dupes.py      colonists: spawning, needs, health, death, movement along a path
    chores.py     what each colonist does next and doing it: choosing, running, cancelling
    chore_common.py    chore plumbing shared below (Chore, cache, goals, machines adapter)
    chore_survival.py  air, food, toilet/floor, washing chores
    chore_jobs.py      operate, build, dig, deconstruct, harvest, empty chores
    chore_haul.py      supply (materials to sites/machines) and haul (debris to storage) chores
    research.py   tech tree (research/*.json) unlocking buildings; Research Station behaviour
    schedule.py   three shared 24-hour schedules (work / downtime / sleep)
    orders.py     player orders (dig, build, sweep, deconstruct, cancel, priority, toggle, filter)
    view.py       public/private state for clients (the wire contract)
    match.py      Match: one colony; clock, pause/speed, step order, log
"""

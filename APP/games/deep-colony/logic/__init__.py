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
    networks.py   power (wires) and liquid pipe networks
    machines.py   behaviour of each building kind (power, oxygen, food, plumbing, heat...)
    nav.py        where colonists can walk/climb, distance maps, paths
    dupes.py      colonists: spawning, needs, health, death, movement along a path
    chores.py     what each colonist does next and doing it (survival, orders, supply, haul)
    orders.py     player orders (dig, build, deconstruct, cancel, priority, toggle)
    view.py       public/private state for clients (the wire contract)
    match.py      Match: one colony; clock, pause/speed, step order, log
"""

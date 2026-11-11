"""Hex Realms: the Explore order, a unit that walks on its own to clear fog of war.

    target(m, uid)    the cell the unit should move to this turn, as its owner sees the map, or None
                      when nothing is left that it can get closer to
    step(m, uid)      give the unit that move (its orders' "moves"); False if there is none

Orders (orders.explore) set the unit's "explore" flag; Match.plan_explorers calls step() for every
flagged unit as each turn's planning starts, until its owner gives it another order (any order for
the unit clears the flag) or step() finds nothing left (the flag is cleared then).

Choosing: among the cells it can end on this turn (movement.reach, never an attack), the one with
the most unexplored cells within the unit's vision; if every reachable cell sees only explored
land, it heads for the nearest unexplored cell it can get closer to (of the GOALS nearest). Ties go
to the smallest key, so it's deterministic. Bots scout with the same target().
"""

from gamekit.hexes import disk, dist, parse

from . import movement, orders
from .content import UNITS

GOALS = 60  # unexplored cells tried as a far goal, nearest first


def target(m, uid):
    u = m.units[uid]
    pid = u["owner"]
    explored = m.explored[pid]
    known = movement.knowledge(m, u)
    options = sorted(k for k in movement.reach(m, uid) if not movement.is_target(m, u, k, known))
    if not options:
        return None
    radius = UNITS[u["type"]]["vision"]
    unknown = {k: sum(1 for c in disk(radius, parse(k)) if c in m.cells and c not in explored) for k in options}
    best = max(options, key=lambda k: unknown[k])  # the first (smallest key) of the best
    if unknown[best]:
        return best
    hidden = sorted((c for c in m.cells if c not in explored), key=lambda c: (dist(c, u["at"]), c))
    for goal in hidden[:GOALS]:  # nearest first; skip ones it can't get closer to (across water...)
        best = min(options, key=lambda k: (dist(k, goal), k))
        if dist(best, goal) < dist(u["at"], goal):
            return best
    return None


def step(m, uid):
    goal = target(m, uid)
    p = goal and movement.path(m, uid, goal)
    if not p:
        return False
    pid = m.units[uid]["owner"]
    orders.clear_unit(m, pid, uid, exploring=True)
    m.orders[pid]["moves"][uid] = p
    return True

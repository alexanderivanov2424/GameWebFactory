"""Hex Realms: where a unit on the Explore standing order walks to clear fog of war.

    target(m, uid)  the cell to move to this turn (owner's view), or None when nothing is left to get closer to

Picks the reachable cell (never an attack) with the most unexplored cells in its vision; if none has
any, heads for the nearest unexplored cell it can get closer to (of GOALS tried). Ties go to the
smallest key.
"""

from gamekit.hexes import disk, dist, parse

from . import movement
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
    for goal in hidden[:GOALS]:  # skip goals it can't get closer to (e.g. across water)
        best = min(options, key=lambda k: (dist(k, goal), k))
        if dist(best, goal) < dist(u["at"], goal):
            return best
    return None


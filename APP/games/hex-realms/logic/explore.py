"""Hex Realms: where a unit on the Explore standing order (standing.py) walks to clear fog of war.

    target(m, uid)    the cell the unit should move to this turn, as its owner sees the map, or None
                      when nothing is left that it can get closer to (the Explore order ends then)

Choosing: among the cells it can end on this turn (movement.reach, never an attack), the one with
the most unexplored cells within the unit's vision; if every reachable cell sees only explored
land, it heads for the nearest unexplored cell it can get closer to (of the GOALS nearest). Ties go
to the smallest key, so it's deterministic. Bots scout with the same target().
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
    for goal in hidden[:GOALS]:  # nearest first; skip ones it can't get closer to (across water...)
        best = min(options, key=lambda k: (dist(k, goal), k))
        if dist(best, goal) < dist(u["at"], goal):
            return best
    return None


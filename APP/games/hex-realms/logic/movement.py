"""Hex Realms: unit paths and simultaneous movement.

Movement points are in half steps: a unit with move 2 has 4. Entering a cell costs its
terrain's "move" (grass 2, forest 4...); naval units move on water only (2 per cell).
Mountains and water stop land units. Own structures can be crossed. A cell with an enemy unit
or enemy structure can only be the last
cell of a path: moving into it is an attack (it costs one step, 2).

    reach(m, uid)          {key: previous key} for every cell the unit can end on this turn, as its
                           owner sees the map (fog: unexplored cells cost 2, hidden enemies are
                           ignored, remembered structures count)
    path(m, uid, to)       [keys] from the next cell to `to`, or None if out of reach
    route(m, uid, goals)   [keys] to the cheapest of `goals` over any number of turns, or None
                           (a step costing more than the unit's whole movement is never taken)
    this_turn(m, uid, keys)  the part of a route the unit can walk this turn
    resolve(m, events)     moves every unit with an order, one cell per step, all at once

Resolution uses the real map: each unit has its real movement points, and stops before a cell
that's impassable or costs more than it has left (fog hid the terrain).

Each step: (1) moving into an enemy structure is a siege; (2) enemy units moving through each
other fight (both attacking); (3) enemy units moving into the same cell fight there (nobody
enters); when one player's units move into the same cell, the lowest id goes and the others try
again next step; (4) units move into free cells (chains of units following each other work);
(5) a unit still blocked by an enemy attacks it (the blocker defends); one blocked by its own
side swaps places with it (when they move into each other's cells) or passes over it (and any
friends behind) to the next free cell on its path, paying for every cell crossed, and otherwise
stops (its path ends on the friend). Any unit that fights stops
for the rest of the turn, wherever it stands.
"""

import heapq

from gamekit.hexes import neighbors

from . import vision
from .combat import battle, siege
from .content import TERRAIN, UNITS

ATTACK_COST = 2


def enemy_structure(m, pid, k):
    sid = m.cell_structure.get(k)
    return sid is not None and m.structures[sid]["owner"] != pid


def step_cost(m, u, k):
    """Cost to enter k as an ordinary step, or None if it can't be entered (attacks aside)."""
    if k not in m.cells:
        return None
    terrain = m.cells[k]
    if UNITS[u["type"]]["naval"]:
        return 2 if terrain == "water" else None
    return TERRAIN[terrain]["move"]


def knowledge(m, u):
    """What u's owner knows when planning: (explored cells, visible cells, {key: (owner, type)})."""
    pid = u["owner"]
    return m.explored[pid], m.visible[pid], vision.known_at(m, pid)


def planned_cost(m, u, k, known):
    """step_cost as the owner believes it: unexplored cells look like open ground (2)."""
    explored, _, structures = known
    if k not in m.cells:
        return None
    if k not in explored:
        return 2
    if UNITS[u["type"]]["naval"]:
        return 2 if m.cells[k] == "water" else None
    return TERRAIN[m.cells[k]]["move"]


def is_target(m, u, k, known):
    """A visible enemy unit or a known attackable enemy structure on k (the end of a path)."""
    _, visible, structures = known
    occ = m.unit_at.get(k)
    if occ is not None and m.units[occ]["owner"] != u["owner"] and k in visible:
        return True
    owner, stype = structures.get(k, (None, None))
    return owner is not None and owner != u["owner"]


def _search(m, u, limited, goals=None):
    """Cheapest paths from u's cell as its owner sees the map: ({key: previous key}, goal reached).
    limited: only cells within this turn's movement. goals: stop at the first of these reached.
    A step that costs more than the unit's whole movement is never taken (a slow unit and a forest)."""
    known = knowledge(m, u)
    budget = UNITS[u["type"]]["move"] * 2
    best, prev = {u["at"]: 0}, {}
    heap = [(0, u["at"])]
    while heap:
        cost, k = heapq.heappop(heap)
        if cost > best[k]:
            continue
        if goals is not None and k in goals and k != u["at"]:
            return prev, k
        if k != u["at"] and is_target(m, u, k, known):
            continue
        for n in neighbors(k):
            if n not in m.cells:
                continue
            if is_target(m, u, n, known):
                c = ATTACK_COST
                if not UNITS[u["type"]]["naval"] and n in known[0] and m.cells[n] == "water":
                    continue
            else:
                c = planned_cost(m, u, n, known)
                if c is None or c > budget:
                    continue
            total = cost + c
            if (not limited or total <= budget) and total < best.get(n, float("inf")):
                best[n], prev[n] = total, k
                heapq.heappush(heap, (total, n))
    return prev, None


def reach(m, uid):
    return _search(m, m.units[uid], True)[0]


def _walk_back(prev, to):
    out = [to]
    while prev.get(out[-1]) in prev:
        out.append(prev[out[-1]])
    return out[::-1]


def path(m, uid, to):
    prev = reach(m, uid)
    if to not in prev:
        return None
    return _walk_back(prev, to)


def route(m, uid, goals):
    """[keys] from the next cell to the cheapest of `goals` to get to, over any number of turns (as
    the owner sees the map), or None if there's no known way."""
    prev, goal = _search(m, m.units[uid], False, set(goals))
    return _walk_back(prev, goal) if goal else None


def this_turn(m, uid, keys):
    """The start of path `keys` that the unit can walk this turn (planned costs)."""
    u = m.units[uid]
    known = knowledge(m, u)
    budget, spent, out = UNITS[u["type"]]["move"] * 2, 0, []
    for k in keys:
        c = ATTACK_COST if is_target(m, u, k, known) else planned_cost(m, u, k, known)
        if c is None or spent + c > budget:
            break
        spent += c
        out.append(k)
    return out


def pass_friends(m, uid, keys, left):
    """Walk over the owner's own units at the front of `keys` to the first free cell after them, in
    one go (cost of every cell crossed). False (nothing moves) if the path ends on a friend, the free
    cell holds an enemy or an enemy structure, or the movement left doesn't cover it."""
    u = m.units[uid]
    cost = 0
    for i, k in enumerate(keys):
        c = step_cost(m, u, k)
        if c is None:
            return False
        cost += c
        occ = m.unit_at.get(k)
        if occ is None:
            break
        if m.units[occ]["owner"] != u["owner"]:
            return False
    else:
        return False
    if occ is not None or cost > left[uid] or enemy_structure(m, u["owner"], k):
        return False
    left[uid] -= cost
    m.move_unit(uid, k)
    del keys[:i + 1]
    return True


def resolve(m, events):
    paths = {uid: list(p) for uid, p in m.orders_moves() if uid in m.units}
    left = {uid: UNITS[m.units[uid]["type"]]["move"] * 2 for uid in paths}  # real movement points
    while True:
        intents = {uid: p[0] for uid, p in sorted(paths.items()) if p and uid in m.units}
        if not intents:
            return

        def stop(uid):
            paths[uid] = []
            intents.pop(uid, None)

        for uid, k in list(intents.items()):  # (1) sieges
            sid = m.cell_structure.get(k)
            if k not in m.unit_at and enemy_structure(m, m.units[uid]["owner"], k):
                siege(m, uid, sid, events)
                stop(uid)
        for uid, k in list(intents.items()):  # (2) moving through each other
            other = m.unit_at.get(k)
            if uid in intents and other in intents and uid in m.units and intents[other] == m.units[uid]["at"] \
                    and m.units[other]["owner"] != m.units[uid]["owner"]:
                stop(uid)
                stop(other)
                battle(m, uid, other, True, True, events)
        groups = {}
        for uid, k in intents.items():
            groups.setdefault(k, []).append(uid)
        for k, uids in groups.items():  # (3) same target
            if len(uids) < 2:
                continue
            owners = {m.units[x]["owner"] for x in uids}
            if len(owners) == 1:  # the lowest id goes first; the others try again next step
                for x in uids[1:]:
                    intents.pop(x)
                continue
            for x in uids:
                stop(x)
            champion = uids[0]
            for x in uids[1:]:
                if champion not in m.units:
                    champion = x
                    continue
                if x in m.units and m.units[x]["owner"] != m.units[champion]["owner"]:
                    battle(m, champion, x, True, True, events)
                    if champion not in m.units:
                        champion = x
        moved = True  # (4) free cells
        while moved:
            moved = False
            for uid, k in sorted(intents.items()):
                if k not in m.unit_at and not enemy_structure(m, m.units[uid]["owner"], k):
                    cost = step_cost(m, m.units[uid], k)
                    if cost is None or cost > left[uid]:  # the real terrain was worse than planned
                        stop(uid)
                        moved = True
                        continue
                    left[uid] -= cost
                    m.move_unit(uid, k)
                    paths[uid].pop(0)
                    intents.pop(uid)
                    moved = True
        for uid, k in sorted(intents.items()):  # (5) blocked
            if uid not in intents or uid not in m.units:
                continue
            u, occ = m.units[uid], m.unit_at.get(k)
            if occ is not None and m.units[occ]["owner"] == u["owner"]:  # a friend: swap or pass through
                here = u["at"]
                if intents.get(occ) == here and step_cost(m, u, k) is not None and \
                        step_cost(m, m.units[occ], here) is not None and \
                        step_cost(m, u, k) <= left[uid] and step_cost(m, m.units[occ], here) <= left[occ]:
                    left[uid] -= step_cost(m, u, k)
                    left[occ] -= step_cost(m, m.units[occ], here)
                    m.move_unit(uid, k)
                    m.move_unit(occ, here)
                    paths[uid].pop(0)
                    paths[occ].pop(0)
                    intents.pop(uid)
                    intents.pop(occ)
                    continue
                if pass_friends(m, uid, paths[uid], left):
                    intents.pop(uid)
                    continue
            stop(uid)
            if occ is not None and m.units[occ]["owner"] != u["owner"]:  # (a target that left: just stop)
                stop(occ)
                battle(m, uid, occ, True, False, events)

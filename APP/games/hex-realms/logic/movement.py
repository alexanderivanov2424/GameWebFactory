"""Hex Realms: unit paths and simultaneous movement.

Movement points are in half steps: a unit with move 2 has 4. Entering a cell costs its
terrain's "move" (grass 2, forest 4...), or ROAD_MOVE (1) on any road; naval units move on
water only (2 per cell). Mountains and water stop land units. Own structures can be crossed;
enemy roads too. A cell with an enemy unit or enemy structure (not a road) can only be the last
cell of a path: moving into it is an attack (it costs one step, 2).

    reach(m, uid)          {key: previous key} for every cell the unit can end on this turn, as its
                           owner sees the map (fog: unexplored cells cost 2, hidden enemies are
                           ignored, remembered structures count)
    path(m, uid, to)       [keys] from the next cell to `to`, or None if out of reach
    resolve(m, events)     moves every unit with an order, one cell per step, all at once

Resolution uses the real map: each unit has its real movement points, and stops before a cell
that's impassable or costs more than it has left (fog hid the terrain).

Each step: (1) moving into an enemy structure is a siege; (2) enemy units moving through each
other fight (both attacking); (3) enemy units moving into the same cell fight there (nobody
enters); same-player collisions let the lowest id through; (4) units move into free cells
(chains of units following each other work); (5) a unit still blocked by an enemy attacks it
(the blocker defends), and one blocked by a friend just stops. Any unit that fights stops
for the rest of the turn, wherever it stands.
"""

import heapq

from gamekit.hexes import neighbors

from . import vision
from .combat import battle, siege
from .content import ROAD, ROAD_MOVE, TERRAIN, UNITS

ATTACK_COST = 2


def enemy_structure(m, pid, k):
    sid = m.cell_structure.get(k)
    return sid is not None and m.structures[sid]["owner"] != pid and m.structures[sid]["type"] != ROAD


def step_cost(m, u, k):
    """Cost to enter k as an ordinary step, or None if it can't be entered (attacks aside)."""
    if k not in m.cells:
        return None
    terrain = m.cells[k]
    if UNITS[u["type"]]["naval"]:
        return 2 if terrain == "water" else None
    sid = m.cell_structure.get(k)
    if sid is not None and m.structures[sid]["type"] == ROAD:
        return ROAD_MOVE
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
    if structures.get(k, (None, None))[1] == ROAD:
        return ROAD_MOVE
    return TERRAIN[m.cells[k]]["move"]


def is_target(m, u, k, known):
    """A visible enemy unit or a known attackable enemy structure on k (the end of a path)."""
    _, visible, structures = known
    occ = m.unit_at.get(k)
    if occ is not None and m.units[occ]["owner"] != u["owner"] and k in visible:
        return True
    owner, stype = structures.get(k, (None, None))
    return owner is not None and owner != u["owner"] and stype != ROAD


def reach(m, uid):
    u = m.units[uid]
    known = knowledge(m, u)
    budget = UNITS[u["type"]]["move"] * 2
    best, prev = {u["at"]: 0}, {}
    heap = [(0, u["at"])]
    while heap:
        cost, k = heapq.heappop(heap)
        if cost > best.get(k, budget + 1) or (k != u["at"] and is_target(m, u, k, known)):
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
                if c is None:
                    continue
            total = cost + c
            if total <= budget and total < best.get(n, budget + 1):
                best[n], prev[n] = total, k
                heapq.heappush(heap, (total, n))
    return prev


def path(m, uid, to):
    prev = reach(m, uid)
    if to not in prev:
        return None
    out = [to]
    while prev.get(out[-1]) in prev:
        out.append(prev[out[-1]])
    return out[::-1]


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
            if len(owners) == 1:
                for x in uids[1:]:
                    stop(x)
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
            occ = m.unit_at.get(k)
            stop(uid)
            if occ is not None and m.units[occ]["owner"] != m.units[uid]["owner"]:  # (a target that left: just stop)
                stop(occ)
                battle(m, uid, occ, True, False, events)

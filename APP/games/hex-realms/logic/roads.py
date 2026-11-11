"""Hex Realms: road networks and roads laid automatically by idle people.

Goods need no roads (logistics.py); roads speed up units (movement.py: ROAD_MOVE per cell) and tie
a realm together. Roads cost nothing but work: a Road ordered by hand is a 1-turn site for 1
builder (construction.py), and every person still idle once the sites have their builders lays one
road cell a turn on their own.

    networks(m, pid)          {sid: {network ids}}: pid's road cells plus "navigable" structures
                              (Market, Storage Yard...), grouped by touching; a network counts only
                              if it holds a road. A structure is on every network it is part of or touches.
    linked(nets, a, b)        structures a and b share a network
    goals(m, pid)             [(structure, goal structures)] oldest first: every non-road structure
                              wants a road to its nearest store (Town Hall, Storage Yard, Granary);
                              stores want their nearest Town Hall; Town Halls want the nearest other Town Hall
    route(m, pid, s, targets) the empty cells of the shortest road from s to one of `targets`
                              (existing roads cost nothing), nearest s first; None if there's none
    lay(m, pid, n, events)    idle people lay up to n road cells: for each unlinked (structure, goal)
                              pair in goals() order, the route's cells from the structure's end, while
                              they're in pid's territory. They're finished at once (the work is this
                              turn's), as one "roads" event.

Automatic roads follow the rules for building a Road (own territory, a road's terrain, no structure
or site there, no enemy unit seen there) and look only at explored cells, so they never give away
what fog hides. A pair is skipped when it touches already (neighbours need no road) or no route exists.
"""

from collections import deque

from gamekit.hexes import dist, neighbors

from .content import ROAD, STRUCTURES, TOWN_HALL
from . import logistics


def networks(m, pid):
    own = [s for s in m.structures.values() if s["owner"] == pid]
    links = {c: s["type"] == ROAD for s in own if s["type"] == ROAD or STRUCTURES[s["type"]]["navigable"] for c in s["cells"]}
    net, has_road = {}, {}
    for start in links:
        if start in net:
            continue
        n = len(has_road) + 1
        net[start], todo, road = n, [start], False
        while todo:
            c = todo.pop()
            road = road or links[c]
            for k in neighbors(c):
                if k in links and k not in net:
                    net[k] = n
                    todo.append(k)
        has_road[n] = road
    return {s["id"]: {net[k] for c in s["cells"] for k in [c] + neighbors(c) if k in net and has_road[net[k]]} for s in own}


def linked(nets, a, b):
    return bool(nets[a["id"]] & nets[b["id"]])


def touching(a, b):
    cells = set(b["cells"])
    return any(n in cells for c in a["cells"] for n in neighbors(c))


def _gap(a, b):
    return min(dist(x, y) for x in a["cells"] for y in b["cells"])


def goals(m, pid):
    own = sorted((s for s in m.structures.values() if s["owner"] == pid and s["type"] != ROAD), key=lambda s: s["n"])
    halls = [s for s in own if s["type"] == TOWN_HALL]
    stores = [s for s in own if logistics.capacity(s)]
    out = []
    for s in own:
        if s["type"] == TOWN_HALL:
            pool = [h for h in halls if h is not s]
        elif logistics.capacity(s):
            pool = halls
        else:
            pool = stores
        if pool:
            best = min(_gap(s, x) for x in pool)
            out.append((s, [x for x in pool if _gap(s, x) == best]))
    return out


def _open(m, pid, k, known):
    """k can take an automatic road (planning view: explored cells, enemy units seen)."""
    if k not in m.cells or k not in known or m.cells[k] not in STRUCTURES[ROAD]["terrain"]:
        return False
    if k in m.cell_structure or k in m.cell_site:
        return False
    owner = m.territory.get(k)
    if owner is not None and owner != pid:
        return False
    occ = m.unit_at.get(k)
    return not (occ is not None and m.units[occ]["owner"] != pid and k in m.visible[pid])


def route(m, pid, s, targets):
    known = m.explored[pid] if m.fog else m.cells
    own_road = {c for x in m.structures.values() if x["owner"] == pid and
                (x["type"] == ROAD or STRUCTURES[x["type"]]["navigable"]) for c in x["cells"]}
    own_road |= {c for x in m.sites.values() if x["owner"] == pid and x["type"] == ROAD for c in x["cells"]}
    goal = {n for t in targets for c in t["cells"] for n in neighbors(c)} | {c for t in targets for c in t["cells"]}
    best, prev, todo = {}, {}, deque()
    for c in s["cells"]:
        for n in neighbors(c):
            if n in own_road or _open(m, pid, n, known):
                cost = 0 if n in own_road else 1
                if cost < best.get(n, 99):
                    best[n], prev[n] = cost, None
                    (todo.appendleft if cost == 0 else todo.append)((cost, n))
    while todo:
        cost, k = todo.popleft()
        if cost > best[k]:
            continue
        if k in goal:
            cells = []
            while k is not None:
                if k not in own_road:
                    cells.append(k)
                k = prev[k]
            return cells[::-1]
        for n in neighbors(k):
            if n in own_road:
                step = 0
            elif _open(m, pid, n, known):
                step = 1
            else:
                continue
            if cost + step < best.get(n, 99):
                best[n], prev[n] = cost + step, k
                (todo.appendleft if step == 0 else todo.append)((cost + step, n))
    return None


def lay(m, pid, n, events):
    built = []
    for s, targets in goals(m, pid):
        if n <= 0:
            break
        if any(touching(s, t) for t in targets):
            continue
        nets = networks(m, pid)
        if any(linked(nets, s, t) for t in targets):
            continue
        cells = route(m, pid, s, targets)
        for c in cells or []:
            if n <= 0 or m.territory.get(c) != pid:
                break
            m.add_structure(pid, ROAD, c, 0)
            built.append(c)
            n -= 1
    if built:
        events.append({"t": "roads", "owner": pid, "cells": built})
    return built

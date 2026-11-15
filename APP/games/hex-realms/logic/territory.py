"""Hex Realms: territory. Strong land comes free from Town Halls; weak land is bought with gold.

    territory(m)                      (new {key: pid}, weak cells still held {key: pid}); Match.refresh stores both
    bought(m, pid)                    weak cells pid pays upkeep for
    give_up(m, pid, n)                drop n weak cells pid can't pay for, farthest from its Town Halls first
    unit_entered(m, uid)              an enemy unit on or next to weak land unclaims it (move_unit/add_unit call it)
    threatened(m, pid, k, seen=None)  an enemy of pid stands on or next to k (seen: only units on those cells)

Strong land: every Town Hall reaches the cells within CITY_RADIUS. First come, first served: a cell
stays with its owner while they still reach it; a free cell goes to the one player reaching it, and
to no one while two or more do. Losing a Town Hall loses its free land.
Weak land (m.claims): bought with orders.claim on cells nobody held. Lost when another player's Town
Hall reaches it, when an enemy unit is on or next to it, or when it isn't connected through its
owner's land to their strong land. Your own Town Hall reaching it makes it strong. Lost weak cells
don't come back on their own. Each costs LAND_UPKEEP gold a turn (economy.py); a realm that can't
pay loses the farthest cells first.
"""

from gamekit.hexes import disk, dist, neighbors, parse

from .content import TOWN_HALL

CITY_RADIUS = 2  # free land around every Town Hall
LAND_UPKEEP = 1  # gold a turn per weak (bought) cell


def _reach(m):
    reach = {}
    for s in m.structures.values():
        if s["type"] != TOWN_HALL:
            continue
        radius = CITY_RADIUS
        for c in s["cells"]:
            for k in disk(radius, parse(c)):
                if k in m.cells:
                    reach.setdefault(k, set()).add(s["owner"])
    return reach


def threatened(m, pid, k, seen=None):
    for c in [k, *neighbors(k)]:
        uid = m.unit_at.get(c)
        if uid is not None and m.units[uid]["owner"] != pid and (seen is None or c in seen):
            return True
    return False


def territory(m):
    reach = _reach(m)
    out = {}
    for k, owners in reach.items():
        cur = m.territory.get(k)
        if cur in owners:
            out[k] = cur
        elif len(owners) == 1:
            out[k] = next(iter(owners))
    # weak land: no Town Hall reach and no enemy next to it
    weak = {k: p for k, p in m.claims.items() if k in m.cells and k not in reach and not threatened(m, p, k)}
    held = {}
    frontier = [(k, p) for k, p in out.items()]
    while frontier:
        k, p = frontier.pop()
        for n in neighbors(k):
            if weak.get(n) == p and n not in held:
                held[n] = p
                frontier.append((n, p))
    out.update(held)
    return out, held


def unit_entered(m, uid):
    u = m.units[uid]
    for k in [u["at"], *neighbors(u["at"])]:
        p = m.claims.get(k)
        if p is not None and p != u["owner"]:
            del m.claims[k]
            if m.territory.get(k) == p:
                del m.territory[k]


def bought(m, pid):
    return sum(1 for p in m.claims.values() if p == pid)


def give_up(m, pid, n):
    halls = [c for s in m.structures_of(pid, TOWN_HALL) for c in s["cells"]]
    mine = sorted((k for k, p in m.claims.items() if p == pid),
                  key=lambda k: (-min((dist(k, h) for h in halls), default=0), k))
    for k in mine[:n]:
        del m.claims[k]
        if m.territory.get(k) == pid:
            del m.territory[k]
    return len(mine[:n])

"""Hex Realms: territory, strong (from Town Halls, free) and weak (bought with gold, with upkeep).

    territory(m)             (the new {key: pid}, the weak cells still held {key: pid}) from
                             m.territory and m.claims; Match.refresh stores both
    bought(m, pid, pending=False)  the weak cells pid pays upkeep for (LAND_UPKEEP each a turn);
                             pending: also the cells pid's claim orders this turn would take (forecast)
    give_up(m, pid, n)       pid can't pay for n cells: drop n weak cells, farthest from pid's Town
                             Halls first; returns how many went
    unit_entered(m, uid)     an enemy unit standing on or next to weak land unclaims it at once
                             (Match.move_unit / add_unit call it, so passing through counts)
    claim_cells(m, at)       the cells a claim at `at` would take: it and its neighbours that are on
                             the map and nobody's
    threatened(m, pid, k, seen=None)  an enemy unit of pid's stands on or next to k (seen: only units
                             on those cells count, for checks made with what pid knows)

Rules:
- Strong land (free, no upkeep): structures don't spread land, except Town Halls: every Town Hall
  reaches the cells within CITY_RADIUS of its cells. First come, first served: a cell stays its owner's while they still reach it, a
  free cell goes to the one player reaching it, and to no one while two or more do (they got
  there at the same time). Losing a Town Hall loses its free land.
- Weak land (m.claims): cells bought with gold (orders.claim) that were nobody's at that moment.
  Lost (back to no one) when:
    * another player's Town Hall reaches it (their strong land overrides it); your own Town Hall
      reaching it turns it into strong land (it leaves m.claims);
    * an enemy unit stands on it or next to it (also blocks claiming it);
    * it isn't connected, through that player's own land, to their strong land.
  Each weak cell costs LAND_UPKEEP gold a turn (economy.py); a realm that can't pay gives up the
  cells it can't pay for, farthest from its Town Halls first (give_up).
Weak cells, once lost, don't come back on their own (buy them again).
"""

from gamekit.hexes import disk, dist, neighbors, parse

from .content import TOWN_HALL

CLAIM_RADIUS = 1  # a claim holds the cell and its free neighbours
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
    # Weak cells: only where no Town Hall reaches, with no enemy unit on or next to them.
    weak = {k: p for k, p in m.claims.items() if k in m.cells and k not in reach and not threatened(m, p, k)}
    # ...and connected to their owner's strong land through their own cells.
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


def claim_cells(m, at):
    return [k for k in disk(CLAIM_RADIUS, parse(at)) if k in m.cells and k not in m.territory]


def bought(m, pid, pending=False):
    cells = {k for k, p in m.claims.items() if p == pid}
    if pending:
        for c in m.orders[pid]["claims"]:
            cells.update(claim_cells(m, c["at"]))
    return len(cells)


def give_up(m, pid, n):
    halls = [c for s in m.structures.values() if s["owner"] == pid and s["type"] == TOWN_HALL for c in s["cells"]]
    mine = sorted((k for k, p in m.claims.items() if p == pid),
                  key=lambda k: (-min((dist(k, h) for h in halls), default=0), k))
    for k in mine[:n]:
        del m.claims[k]
        if m.territory.get(k) == pid:
            del m.territory[k]
    return len(mine[:n])

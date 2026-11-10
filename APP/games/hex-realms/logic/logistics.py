"""Hex Realms: goods (food, wood, stone, metal) kept in storage structures and moved along roads.

Gold, faith and science are realm-wide (players[pid]["res"], never stored anywhere). Goods live in
structures: each storage structure (Town Hall, Storage Yard, Granary: content "storage" / "store")
has a "stock" up to its capacity, and each producer flagged "road" keeps a "held" buffer of at
most one turn's output (making more while full is wasted).

Road networks: a player's road cells plus their "navigable" structures (Market, Storage Yard...),
grouped by touching; a network counts only if it holds at least one road. A structure is on every
network it is part of or touches (so B - navigable A - road links B, and so does B - A - A - road).

    networks(m, pid)          {sid: {network ids}} for pid's structures
    usable(m, pid, nets)      pid's stores whose goods can be spent: every Town Hall, plus stores
                              sharing a network with one (Town Halls first, then oldest)
    stock(m, pid)             {res: amount} pid can spend now: goods in usable stores + gold/faith/science
    capacity(s)               {good: room} of one storage structure (empty if it isn't one)
    take(m, pid, cost)        spend (LobbyError if short): goods from usable stores, in usable() order
    give(m, pid, amounts)     add (refunds, trades): goods into usable stores with room; what doesn't
                              fit goes into the first usable store anyway (a refund is never lost)
    room(m, pid, good)        free space for `good` in usable stores
    deliver(m, pid, nets)     end of turn: every producer's held goods go to the stores on its
                              networks (usable ones first); returns {good: amount} that reached usable
                              stores. A store that isn't usable still fills up; its goods become
                              spendable once a road joins it to a Town Hall's network.
"""

from gamekit import LobbyError
from gamekit.hexes import neighbors

from .content import CAPPED, ROAD, STRUCTURES, TOWN_HALL

GOODS = CAPPED


def capacity(s):
    d = STRUCTURES[s["type"]]
    caps = {r: d["storage"] + d["store"].get(r, 0) for r in GOODS}
    return {r: n for r, n in caps.items() if n > 0}


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


def _stores(m, pid):
    return sorted((s for s in m.structures.values() if s["owner"] == pid and capacity(s)),
                  key=lambda s: (s["type"] != TOWN_HALL, s["n"]))


def usable(m, pid, nets=None):
    nets = networks(m, pid) if nets is None else nets
    hall_nets = set().union(*(nets[s["id"]] for s in m.structures.values() if s["owner"] == pid and s["type"] == TOWN_HALL))
    return [s for s in _stores(m, pid) if s["type"] == TOWN_HALL or nets[s["id"]] & hall_nets]


def stock(m, pid, stores=None):
    out = dict(m.players[pid]["res"])
    for r in GOODS:
        out[r] = 0
    for s in usable(m, pid) if stores is None else stores:
        for r, n in s["stock"].items():
            out[r] += n
    return out


def room(m, pid, good, stores=None):
    return sum(max(0, capacity(s).get(good, 0) - s["stock"].get(good, 0)) for s in (usable(m, pid) if stores is None else stores))


def take(m, pid, cost):
    stores = usable(m, pid)
    have = stock(m, pid, stores)
    short = [r for r, n in cost.items() if have.get(r, 0) < n]
    if short:
        raise LobbyError(f"Not enough {', '.join(short)}.")
    for r, n in cost.items():
        if r not in GOODS:
            m.players[pid]["res"][r] -= n
            continue
        for s in stores:
            used = min(n, s["stock"].get(r, 0))
            if used:
                s["stock"][r] -= used
                n -= used
    return True


def fill(s, good, amount):
    """Put up to `amount` of good into store s; returns what didn't fit."""
    free = max(0, capacity(s).get(good, 0) - s["stock"].get(good, 0))
    put = min(free, amount)
    if put:
        s["stock"][good] = s["stock"].get(good, 0) + put
    return amount - put


def give(m, pid, amounts):
    stores = usable(m, pid)
    for r, n in amounts.items():
        if r not in GOODS:
            m.players[pid]["res"][r] = m.players[pid]["res"].get(r, 0) + n
            continue
        for s in stores:
            n = fill(s, r, n)
        if n and stores:
            stores[0]["stock"][r] = stores[0]["stock"].get(r, 0) + n


def deliver(m, pid, nets):
    stores = _stores(m, pid)
    usable_ids = {s["id"] for s in usable(m, pid, nets)}
    stores.sort(key=lambda s: s["id"] not in usable_ids)  # stable: usable first, then the rest in order
    arrived = {r: 0 for r in GOODS}
    for p in sorted((s for s in m.structures.values() if s["owner"] == pid and s["held"]), key=lambda s: s["n"]):
        targets = [s for s in stores if nets[s["id"]] & nets[p["id"]]]
        for r in list(p["held"]):
            n = p["held"][r]
            for s in targets:
                left = fill(s, r, n)
                if s["id"] in usable_ids:
                    arrived[r] += n - left
                n = left
            if n:
                p["held"][r] = n
            else:
                del p["held"][r]
    return arrived

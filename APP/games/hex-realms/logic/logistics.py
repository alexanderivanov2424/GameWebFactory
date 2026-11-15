"""Hex Realms: goods (wood, stone, metal) kept in storage structures. Food is never stored (economy.py).

Gold, faith and science are realm-wide (players[pid]["res"]). Storage structures (Town Hall, Storage
Yard) hold a "stock" up to their capacity. At end of turn, what's left of production after
upkeep (economy.end_of_turn) fills the stores with room (Town Halls first, then oldest); the rest is lost.

    stores(m, pid)           pid's storage structures, in fill order
    stock(m, pid)            {res: amount} spendable now
    capacity(s)              {good: room} of one storage structure
    room(m, pid, good)       free space for good in pid's stores
    take(m, pid, cost)       spend (LobbyError if short), goods from stores first
    store(m, pid, good, n)   put produce in; returns what didn't fit
    give(m, pid, amounts)    add (refunds, trades); what doesn't fit goes into the first store anyway
"""

from gamekit import LobbyError

from .content import CAPPED, STRUCTURES, TOWN_HALL

GOODS = CAPPED


def capacity(s):
    d = STRUCTURES[s["type"]]
    caps = {r: d["storage"] + d["store"].get(r, 0) for r in GOODS}
    return {r: n for r, n in caps.items() if n > 0}


def stores(m, pid):
    return sorted((s for s in m.structures_of(pid) if capacity(s)),
                  key=lambda s: (s["type"] != TOWN_HALL, s["n"]))


def stock(m, pid):
    out = dict(m.players[pid]["res"])
    for r in GOODS:
        out[r] = 0
    for s in stores(m, pid):
        for r, n in s["stock"].items():
            out[r] += n
    return out


def room(m, pid, good):
    return sum(max(0, capacity(s).get(good, 0) - s["stock"].get(good, 0)) for s in stores(m, pid))


def take(m, pid, cost):
    have = stock(m, pid)
    short = [r for r, n in cost.items() if have.get(r, 0) < n]
    if short:
        raise LobbyError(f"Not enough {', '.join(short)}.")
    own = stores(m, pid)
    for r, n in cost.items():
        if r not in GOODS:
            m.players[pid]["res"][r] -= n
            continue
        for s in own:
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


def store(m, pid, good, n, own=None):
    for s in stores(m, pid) if own is None else own:
        n = fill(s, good, n)
    return n


def give(m, pid, amounts):
    own = stores(m, pid)
    for r, n in amounts.items():
        if r not in GOODS:
            m.players[pid]["res"][r] = m.players[pid]["res"].get(r, 0) + n
            continue
        n = store(m, pid, r, n, own)
        if n and own:
            own[0]["stock"][r] = own[0]["stock"].get(r, 0) + n

"""Conveyors: belt tiles that carry goods from processors to markets and to other processors.

Match.belts = {lot: Belt}. A belt belongs to the player who laid it (pid; removed when they leave),
points one way (dir 0 right, 1 down, 2 left, 3 up) at its next lot and holds up to CAP goods as a
queue of runs [[good, n], ...] (front = next to leave). The goods on a belt are its owner's.
Laying (lay): on reached lots with nothing built (not the cabin or a landmark), BELT_COST each,
from the layer's cash; a lot with your own belt only turns it to the new direction (free).
Every tick (step), downstream belts first (order rebuilt when belts change), each belt moves up to
rate x dt goods (BELT_RATE x its owner's belt_mult upgrades; fractions carry over) off its front:
    into the next belt if it's the same owner's and has room;
    into a market (a cabin lot or an Old Rail Station): sold for the owner, value x goods_mult;
    into the owner's processor that uses that good, while its input has room;
    anything else (nothing there, someone else's belt or processor, a processor that wants
    something else, a full belt) blocks it.
Processors put their goods on belts (offload): each tick a processor whose goods no processor
next to it uses pushes goods onto every belt of its owner beside it (4 sides) that doesn't point
back into it.
Demolishing a belt (demolish.py) loses its goods and refunds part of BELT_COST.
public(): {"<lot>": [dir, front good id or "", goods on it, owner pid]} for the client.
"""

import math

from gamekit import LobbyError

from .content import GOODS, MACHINES

DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))
BELT_COST = 40
BELT_RATE = 10
CAP = 8
MAX_LOTS = 200
SIDES = ((1, 0), (0, 1), (-1, 0), (0, -1))


class Belt:
    def __init__(self, direction, pid):
        self.pid = pid
        self.dir = direction
        self.items = []     # [[good, n]]
        self.count = 0
        self.acc = 0.0

    def push(self, good, n):
        if self.items and self.items[-1][0] == good:
            self.items[-1][1] += n
        else:
            self.items.append([good, n])
        self.count += n

    def pop(self, n):
        self.items[0][1] -= n
        self.count -= n
        if self.items[0][1] <= 0:
            self.items.pop(0)


def next_lot(world, i, direction):
    x, y = world.xy(i)
    dx, dy = DIRS[direction]
    return world.index(x + dx, y + dy)


def lay(match, pid, lots):
    """Lay belts on [x, y, dir] lots (turning existing ones). Refuses if nothing could be done."""
    p = match.player(pid)
    world = match.world
    done, broke, bad = 0, False, None
    for x, y, d in lots[:MAX_LOTS]:
        i = world.index(x, y)
        if d not in range(4):
            raise LobbyError("Bad direction.")
        if i is None:
            continue
        if i in match.belts:
            if match.belts[i].pid != pid:
                bad = f"That conveyor is {match.names.get(match.belts[i].pid, 'someone else')}'s."
                continue
            match.belts[i].dir = d
            match.belt_order = None
            done += 1
            continue
        if not world.reached[i] or world.kind[i] in ("cabin", "site"):
            bad = "Conveyors go on cleared ground (not the cabin or ruins)."
            continue
        if match.occupied(i):
            bad = "Something is already built there."
            continue
        if BELT_COST > p.cash + 1e-9:
            broke = True
            break
        p.cash -= BELT_COST
        match.belts[i] = Belt(d, pid)
        match.belt_order = None
        done += 1
    if not done:
        raise LobbyError("Not enough cash for conveyors." if broke else bad or "Nothing to lay there.")
    return done


def _order(match):
    """Belt lots, downstream first (distance along belts to where the line ends)."""
    belts, world = match.belts, match.world
    depth = {}
    for start in belts:
        chain, seen, i = [], set(), start
        while i in belts and i not in depth and i not in seen:
            chain.append(i)
            seen.add(i)
            i = next_lot(world, i, belts[i].dir)
        base = depth.get(i, -1) if i not in seen else -1   # ends, or loops back on itself
        for k, j in enumerate(reversed(chain)):
            depth[j] = base + 1 + k
    return sorted(belts, key=lambda i: depth[i])


def rate(player):
    return BELT_RATE * player.effect("belt_mult")


def step(match, dt):
    if not match.belts:
        return
    if match.belt_order is None:
        match.belt_order = _order(match)
    world, belts = match.world, match.belts
    speeds = {pid: rate(p) for pid, p in match.players.items()}
    procs = {u.home: u for u in match.units.values() if u.home is not None}
    markets = set(match.markets)
    for i in match.belt_order:
        b = belts.get(i)
        if b is None or b.pid not in match.players:
            continue
        if not b.count:
            b.acc = 0.0
            continue
        owner = match.players[b.pid]
        b.acc = min(b.acc + speeds[b.pid] * dt, float(CAP))
        n = math.floor(b.acc + 1e-9)
        j = next_lot(world, i, b.dir)
        while n > 0 and b.items and j is not None:
            good, have = b.items[0]
            amount = min(n, have)
            if j in belts:
                amount = min(amount, CAP - belts[j].count) if belts[j].pid == b.pid else 0
                if amount > 0:
                    belts[j].push(good, amount)
            elif world.kind[j] == "cabin" or j in markets:
                owner.sell_goods(amount * GOODS[good]["value"])
            elif j in procs and procs[j].pid == b.pid and _takes(procs[j], good):
                proc = procs[j]
                amount = min(amount, math.floor(MACHINES[proc.mid]["params"].get("buffer", 100) - proc.inbox))
                if amount > 0:
                    proc.inbox += amount
            else:
                amount = 0
            if amount <= 0:
                break
            b.pop(amount)
            b.acc -= amount
            n -= amount


def _takes(proc, good):
    m = MACHINES[proc.mid]
    return m["kind"] == "processor" and m["recipe"]["in"] == good


def offload(match, unit, good):
    """Processor unit puts its goods on the belts beside it (not ones pointing back into it)."""
    world = match.world
    x, y = world.xy(unit.home)
    for dx, dy in SIDES:
        if unit.outbox < 1:
            return
        j = world.index(x + dx, y + dy)
        b = match.belts.get(j) if j is not None else None
        if b is None or b.pid != unit.pid or next_lot(world, j, b.dir) == unit.home:
            continue
        n = min(int(unit.outbox), CAP - b.count)
        if n > 0:
            b.push(good, n)
            unit.outbox -= n


def remove(match, i):
    if match.belts.pop(i, None) is not None:
        match.belt_order = None


def remove_player(match, pid):
    for i in [i for i, b in match.belts.items() if b.pid == pid]:
        remove(match, i)


def value_on_belts(match, pid):
    return sum(n * GOODS[g]["value"] for b in match.belts.values() if b.pid == pid for g, n in b.items)


def public(match):
    return {str(i): [b.dir, b.items[0][0] if b.items else "", b.count, b.pid] for i, b in match.belts.items()}

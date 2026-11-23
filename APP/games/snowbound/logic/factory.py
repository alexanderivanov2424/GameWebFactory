"""Factory: processors that turn snow into goods, and the sleds that sell goods at a market.

processor (placed; content recipe {"in", "per", "out"}, params buffer / store / sell):
    unit.inbox holds input (up to params.buffer), unit.outbox finished goods (up to params.store).
    Snow comes from its owner's hauling machines (hauling.py). A processor whose input is a good
    pulls it from its owner's processors next to it (within CHAIN_REACH, diagonals too) that make
    that good, so chains are built by placing them side by side (Brick Press -> Igloo Workshop).
    Each second it turns up to `rate` input (x machine_mult upgrades) into outputs, `per` input
    each. params.sell: outputs are sold on the spot instead of stored (Snow Cone Stand).
    States: working | idle (no input) | full (outbox full) | stalled (no diesel, units.step).
sled (Cargo Sled, Freight Truck, Reindeer Team): carries up to `carry` goods
    (x Player.carry_mult). Picks its owner's processor with the most goods waiting (not one that
    feeds a processor next to it, and not one other sleds already cover), fetches them (trip
    "fetch"), then takes them to the nearest market (trip "home": the cabin or an Old Rail
    Station) and sells them for their value x Player.goods_mult. Routes as in hauling.py.
"""

import math

from .content import GOODS, MACHINES
from .hauling import capacity, plan_home, plan_out, travel

CHAIN_REACH = 1.5
PICKUP_SHARE = 0.2   # a sled waits for this share of a processor's store (or a full load) before fetching
AROUND = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def recipe(unit):
    m = MACHINES[unit.mid]
    return m["recipe"] if m["kind"] == "processor" else None


def neighbours(ctx, unit):
    """Placed units of the same owner next to unit's lot."""
    world = ctx.world
    x, y = world.xy(unit.home)
    for dx, dy in AROUND:
        j = world.index(x + dx, y + dy)
        other = ctx.placed.get(j) if j is not None else None
        if other is not None and other.pid == unit.pid:
            yield other


def feeds(ctx, unit):
    """Does a processor next to unit use what unit makes?"""
    out = recipe(unit)["out"]
    return any((recipe(o) or {}).get("in") == out for o in neighbours(ctx, unit))


def processor(ctx, unit, player, rate):
    m = MACHINES[unit.mid]
    rec, p = m["recipe"], m["params"]
    buffer, store = p.get("buffer", 100), p.get("store", 100)
    if rec["in"] != "snow":
        for other in neighbours(ctx, unit):
            if (recipe(other) or {}).get("out") == rec["in"] and other.outbox > 0:
                take = min(other.outbox, math.floor(buffer - unit.inbox))
                if take > 0:
                    other.outbox -= take
                    unit.inbox += take
    sell = p.get("sell")
    room = math.inf if sell else store - unit.outbox
    amount = min(rate * ctx.dt, unit.inbox, max(0.0, room - unit.acc) * rec["per"])
    if amount <= 1e-9:
        unit.state = "full" if room < 1 else "idle"
        return
    unit.state = "working"
    unit.inbox -= amount
    unit.acc += amount / rec["per"]
    made = math.floor(unit.acc + 1e-9)
    if made:
        unit.acc -= made
        if sell:
            player.sell_goods(made * GOODS[rec["out"]]["value"])
        else:
            unit.outbox += made


def _cargo_count(unit):
    return sum(unit.cargo.values())


def _pick(ctx, unit, player, room):
    """The processor this sled should fetch from, or None."""
    best, best_score = None, 0.0
    for proc in ctx.match.units.values():
        if proc.pid != unit.pid or proc.home is None or recipe(proc) is None or proc.outbox < 1:
            continue
        store = MACHINES[proc.mid]["params"].get("store", 100)
        need = max(1, min(room, store * PICKUP_SHARE))
        waiting = proc.outbox - ctx.fetching.get(proc.id, 0) * room
        if waiting < need or feeds(ctx, proc):
            continue
        value = min(waiting, room) * GOODS[recipe(proc)["out"]]["value"]
        score = value / (math.hypot(proc.x - unit.x, proc.y - unit.y) + 10)
        if score > best_score:
            best, best_score = proc, score
    return best


def sled(ctx, unit, player, rate):
    match, world = ctx.match, ctx.world
    speed = MACHINES[unit.mid]["speed"]
    room = math.floor(capacity(player, unit.mid) - _cargo_count(unit))
    if unit.trip == "home":
        unit.state = "hauling"
        if travel(world, unit, speed, unit.dest[1], ctx.dt):
            value = sum(n * GOODS[g]["value"] for g, n in unit.cargo.items())
            player.sell_goods(value)
            unit.cargo = {}
            unit.trip, unit.dest, unit.path = None, None, []
        return
    if unit.trip == "fetch":
        proc = match.units.get(unit.dest[1])
        if proc is None or proc.pid != unit.pid:
            unit.trip, unit.dest, unit.path = None, None, []
            return
        unit.state = "moving"
        if travel(world, unit, speed, proc.home, ctx.dt):
            take = min(int(proc.outbox), room)
            if take > 0:
                good = recipe(proc)["out"]
                proc.outbox -= take
                unit.cargo[good] = unit.cargo.get(good, 0) + take
            unit.trip = None
            if unit.cargo:
                plan_home(match, unit, player, goods=True)
        return
    proc = _pick(ctx, unit, player, room) if room >= 1 else None
    if proc is not None:
        unit.trip, unit.dest = "fetch", ("proc", proc.id)
        ctx.fetching[proc.id] = ctx.fetching.get(proc.id, 0) + 1
        plan_out(match, unit, proc.home)
        unit.state = "moving"
    elif unit.cargo:
        plan_home(match, unit, player, goods=True)
    else:
        unit.state = "idle"

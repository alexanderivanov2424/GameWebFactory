"""Factory: processors that turn snow into goods (conveyors.py moves the goods).

processor (placed; content recipe {"in", "per", "out"}, params buffer / store / sell):
    unit.inbox holds input (up to params.buffer), unit.outbox finished goods (up to params.store).
    The factory is shared: snow comes from anyone's hauling machines (hauling.py), and a processor
    whose input is a good pulls it from any processor next to it (within CHAIN_REACH, diagonals too) that make
    that good, so chains are built by placing them side by side (Brick Press -> Igloo Workshop).
    Each second it turns up to `rate` input (x machine_mult upgrades) into outputs, `per` input
    each. params.sell: outputs are sold on the spot instead of stored (Snow Cone Stand).
    States: working | idle (no input) | full (outbox full) | stalled (no diesel, units.step).
Goods leave a processor on conveyors: each tick it offloads onto the belts beside it
    (conveyors.offload) unless a processor next to it uses what it makes; belts also feed
    processors whose input they carry.
"""

import math

from . import conveyors
from .content import GOODS, MACHINES

CHAIN_REACH = 1.5
AROUND = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]


def recipe(unit):
    m = MACHINES[unit.mid]
    return m["recipe"] if m["kind"] == "processor" else None


def neighbours(ctx, unit):
    """Placed units next to unit's lot (anyone's)."""
    world = ctx.world
    x, y = world.xy(unit.home)
    for dx, dy in AROUND:
        j = world.index(x + dx, y + dy)
        other = ctx.placed.get(j) if j is not None else None
        if other is not None:
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
    if unit.outbox >= 1 and not feeds(ctx, unit):
        conveyors.offload(ctx.match, unit, rec["out"])
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

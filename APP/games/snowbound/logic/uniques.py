"""Unique machines: the helpers landmarks give (landmarks.py), one function per kind.
STEPS[kind](ctx, unit, player, rate) like machines.py.

mammoth  (Woolly Mammoth, unique) digs like a worker, and every dig also hits the 8 lots around it.
spirit   (Snow Spirit, unique, params.fly) digs snowed-over lots, else lots with at most
         params.shallow snow, anywhere in the valley (ignores the rally point).
bernard  (St. Bernard, unique) follows its owner; anyone within params.heat of it stays warm
         (survival.near_heat) and its owner eats params.food/s while below params.hungry food.
golem    (Snow Golem, unique) every params.every s walks to the lowest road below params.max
         within params.range of its owner's rally point (or itself) and raises it one level, free.
spring   (Hot Spring, unique, placed) melts rate from every lot within params.radius (paid) and
         warms anyone within params.heat (survival.near_heat). Burns nothing.
"""

import math

from .content import MACHINES
from .units import collect, move_toward, work


def _params(unit):
    return MACHINES[unit.mid]["params"]


def mammoth(ctx, unit, player, rate):
    world = ctx.world

    def stomp(i, removed, cleared):
        if not removed:
            return
        x, y = world.xy(i)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                j = world.index(x + dx, y + dy)
                if (dx or dy) and j is not None and world.workable(j):
                    got, found = world.dig(j, removed)
                    collect(unit, player, got)
                    if found:
                        ctx.match.found(player.id, found, j)

    work(ctx, unit, player, rate * ctx.dt, on_dig=stomp)


def spirit(ctx, unit, player, rate):
    world = ctx.world
    shallow = _params(unit).get("shallow", 60)
    ok = lambda i: i in world.dusted or world.snow[i] <= shallow  # noqa: E731
    work(ctx, unit, player, rate * ctx.dt, ok=ok, anywhere=True)


def bernard(ctx, unit, player, rate):
    p = _params(unit)
    near = math.hypot(player.x - unit.x, player.y - unit.y)
    if near > 1.2:
        move_toward(ctx.world, unit, player.x, player.y, max(MACHINES[unit.mid]["speed"], 5.0), ctx.dt, 1.0)
        unit.state = "moving"
    else:
        unit.state = "working"
    if near <= 2 and player.food < p.get("hungry", 60):
        player.food = min(100.0, player.food + p.get("food", 3) * ctx.dt)


def golem(ctx, unit, player, rate):
    world, p = ctx.world, _params(unit)
    top = int(p.get("max", 3))
    unit.cd = max(0.0, unit.cd - ctx.dt)
    if unit.lot is not None and not 0 < world.road[unit.lot] < top:
        unit.lot = None
    if unit.lot is None:
        if unit.cd > 0:
            unit.state = "idle"
            return
        rally = ctx.rallies.get(unit.pid)
        cx, cy = rally if rally is not None else (math.floor(unit.x), math.floor(unit.y))
        r = int(p.get("range", 14))
        best, best_key = None, None
        for y in range(max(0, cy - r), min(world.h, cy + r + 1)):
            for x in range(max(0, cx - r), min(world.w, cx + r + 1)):
                i = y * world.w + x
                level = world.road[i]
                if 0 < level < top and world.kind[i] != "cabin":
                    key = (level, (x - cx) ** 2 + (y - cy) ** 2)
                    if best_key is None or key < best_key:
                        best, best_key = i, key
        if best is None:
            unit.cd = p.get("every", 4)
            unit.state = "idle"
            return
        unit.lot = best
    x, y = world.xy(unit.lot)
    if move_toward(world, unit, x + 0.5, y + 0.5, MACHINES[unit.mid]["speed"], ctx.dt) > 0.2:
        unit.state = "moving"
        return
    world.make_road(unit.lot, world.road[unit.lot] + 1)
    unit.lot = None
    unit.cd = p.get("every", 4)
    unit.state = "working"


def spring(ctx, unit, player, rate):
    world, match = ctx.world, ctx.match
    unit.state = "working"
    hx, hy = world.xy(unit.home)
    r = int(_params(unit).get("radius", 4))
    for y in range(hy - r, hy + r + 1):
        for x in range(hx - r, hx + r + 1):
            i = world.index(x, y)
            if i is None or (x - hx) ** 2 + (y - hy) ** 2 > r * r + 0.5 or world.snow[i] <= 0 or world.kind[i] == "cabin":
                continue
            removed, found = world.melt(i, rate * ctx.dt)
            collect(unit, player, removed)
            if found:
                match.found(player.id, found, i)

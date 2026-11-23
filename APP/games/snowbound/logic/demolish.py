"""Demolishing: tearing down what the team built for REFUND of what it cost.

demolish(match, pid, lots, roads_only): for each [x, y] lot, takes away the first of these found:
    a placed machine     refund REFUND x what that copy cost (content.machine_cost at one fewer
                         owned); the team owns one fewer, so the next one costs that again. A
                         processor's stored input and goods are lost. Landmark buildings (unique
                         machines) can't be torn down.
    a Snow Depot         REFUND x the price of the last depot; next depots cost less again.
    a warming hut        REFUND x the price of the last hut.
    a road               removed entirely; REFUND x the cost of the level players paid for
                         (World.paid: tracks dug by machines and Snow Golem upgrades refund nothing).
roads_only: only roads are taken (a drag with the demolish tool), so a drag never flattens
buildings. The cabin and Old Rail Stations can't be demolished. Demolishing a depot or a road
marks the route fields stale (roads.Network rebuilds them). Raises LobbyError when nothing on
the given lots could be demolished. Returns the refund.
"""

import math

from gamekit import LobbyError

from .content import MACHINES, machine_cost
from .hauling import DEPOT_COST, DEPOT_GROWTH
from .roads import LEVELS, MAX_LOTS

REFUND = 0.25


def refunds(match):
    """What tearing down the next hut or depot gives back (for the client)."""
    from .match import HUT_COST, HUT_GROWTH  # match imports this module
    hut = REFUND * HUT_COST * HUT_GROWTH ** (len(match.huts) - 1) if match.huts else 0
    depot = REFUND * DEPOT_COST * DEPOT_GROWTH ** (len(match.depots) - 1) if match.depots else 0
    return {"share": REFUND, "hut": round(hut), "depot": round(depot)}


def machine_refund(match, mid):
    owned = match.stores.owned[mid]
    return round(REFUND * machine_cost(mid, owned - 1)) if owned else 0


def demolish(match, pid, lots, roads_only=False):
    p = match.player(pid)
    world = match.world
    total, done, refused = 0.0, 0, None
    for x, y in lots[:MAX_LOTS]:
        i = world.index(x, y)
        if i is None:
            continue
        got, why = (_road(match, i) if roads_only else _one(match, p, i))
        if why:
            refused = why
            continue
        if got is not None:
            total += got
            done += 1
    if not done:
        raise LobbyError(refused or "There's nothing here to tear down.")
    p.cash += total
    return total


def _one(match, p, i):
    """Demolish the top thing on lot i: (refund, None), (None, None) if empty, (None, why) if refused."""
    world = match.world
    if world.kind[i] == "cabin":
        return None, "The cabin stays."
    if i in match.markets:
        return None, "The Old Rail Station can't be torn down."
    unit = next((u for u in match.units.values() if u.home == i), None)
    if unit is not None:
        m = MACHINES[unit.mid]
        if m["unique"]:
            return None, f"The {m['name']} came from a landmark: it can't be torn down."
        got = machine_refund(match, unit.mid)
        match.stores.owned[unit.mid] -= 1
        del match.units[unit.id]
        match.say(f"{p.name} tore down a {m['name']} (+${got:,}).")
        return got, None
    if i in match.depots:
        got = refunds(match)["depot"]
        match.depots.remove(i)
        match.roads.remove_drop(i)
        match.say(f"{p.name} tore down a Snow Depot (+${got:,}).")
        return got, None
    xy = world.xy(i)
    if xy in match.huts:
        got = refunds(match)["hut"]
        match.huts.remove(xy)
        match.say(f"{p.name} tore down a warming hut (+${got:,}).")
        return got, None
    return _road(match, i)


def _road(match, i):
    world = match.world
    if not world.road[i]:
        return None, None
    got = math.floor(REFUND * LEVELS[world.paid[i]]["cost"])
    world.remove_road(i)
    match.roads.stale = True
    return got, None

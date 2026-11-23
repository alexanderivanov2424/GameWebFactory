"""Hauling: machines with a "carry" carry the snow they dig and are paid when they unload it.

A hauling machine digs as usual (units.collect() adds the snow to unit.load and counts it as
cleared) until its load is full (carry x Player.carry_mult), or it has snow and nothing left to
dig. Then it goes home (trip "home") to the best drop point:
    - the cabin, a Snow Depot or an Old Rail Station: the snow sells for $1 a unit;
    - one of its owner's processors that takes snow and has room for the whole load (factory.py),
      chosen while it is at most PREFER x as far as the best drop point (processing pays more).
After unloading it goes back (trip "back") to the lot where it filled up and carries on.
Changing your rally point cancels trips back.

Routes (plan_home / plan_out): straight off-road, or straight to a road lot within ACCESS and
then along the road network (roads.Field next pointers), whichever is cheaper by the field's
costs. Going back reverses a route from the drop point the field leads to. Paths are lists of
lot indices kept reversed (the next waypoint is last, popped when reached).

Snow Depots (build_depot): built where you stand by anyone, on reached ground, at least
DEPOT_SPACING lots from the cabin and other drop points; DEPOT_COST x DEPOT_GROWTH per depot
already built, at most MAX_DEPOTS. Shared: every player's machines unload at every depot.
"""

import math

from gamekit import LobbyError

from .content import MACHINES
from .roads import INF, nearest_road

ACCESS = 6
PREFER = 1.25
DEPOT_COST = 400
DEPOT_GROWTH = 1.7
DEPOT_SPACING = 6
MAX_DEPOTS = 40


def capacity(player, mid):
    return MACHINES[mid]["carry"] * player.carry_mult(mid)


def lot_of(world, unit):
    return world.index(min(world.w - 1, max(0, math.floor(unit.x))), min(world.h - 1, max(0, math.floor(unit.y))))


def travel(world, unit, speed, dest, dt):
    """Move along unit.path, then straight to lot dest's centre. True once there."""
    from .units import lot_mult  # units imports this module
    fly = MACHINES[unit.mid]["params"].get("fly")
    left = dt
    for _ in range(100):
        target = unit.path[-1] if unit.path else dest
        tx, ty = world.xy(target)
        tx, ty = tx + 0.5, ty + 0.5
        dist = math.hypot(tx - unit.x, ty - unit.y)
        v = speed * lot_mult(world, lot_of(world, unit), fly)
        if dist <= v * left + 1e-9:
            unit.x, unit.y = tx, ty
            left -= dist / v
            if not unit.path:
                return True
            unit.path.pop()
            if left <= 1e-9:
                return False
        else:
            unit.x += (tx - unit.x) / dist * v * left
            unit.y += (ty - unit.y) / dist * v * left
            return False
    return False


def snow_room(proc):
    m = MACHINES[proc.mid]
    if m["kind"] != "processor" or m["recipe"]["in"] != "snow":
        return 0
    return m["params"].get("buffer", 0) - proc.inbox


def plan_home(match, unit, player, procs=True):
    """Choose where unit unloads and its route there: sets trip "home", dest and path."""
    world = match.world
    field = match.roads.drop
    sources = set(match.roads.drops)  # (a demolished depot may linger in the field until it's rebuilt)
    ux, uy = unit.x - 0.5, unit.y - 0.5
    best, dest, path = INF, None, []
    for s in sources:
        sx, sy = world.xy(s)
        d = math.hypot(sx - ux, sy - uy)
        if d < best:
            best, dest = d, ("drop", s)
    for j, d in nearest_road(field, ux, uy, ACCESS):
        c = d + field.cost[j]
        if c < best - 1e-9 and field.src[j] in sources:
            best, dest, path = c, ("drop", field.src[j]), field.chain(j)[::-1]
    if procs:
        near, near_d = None, best * PREFER
        for proc in match.units.values():
            if proc.pid == unit.pid and proc.home is not None and snow_room(proc) >= unit.load:
                d = math.hypot(proc.x - unit.x, proc.y - unit.y)
                if d <= near_d:
                    near, near_d = proc, d
        if near is not None:
            dest, path = ("proc", near.id), []
    unit.trip, unit.dest, unit.path = "home", dest, path


def plan_out(match, unit, goal):
    """Route from where unit is (usually a drop point) to lot goal: sets unit.path."""
    world, field = match.world, match.roads.drop
    gx, gy = world.xy(goal)
    ux, uy = unit.x - 0.5, unit.y - 0.5
    best, path = math.hypot(gx - ux, gy - uy), []
    for j, d in nearest_road(field, gx, gy, ACCESS):
        sx, sy = world.xy(field.src[j])
        c = math.hypot(sx - ux, sy - uy) + field.cost[j] + d
        if c < best - 0.5:
            best, path = c, field.chain(j)
    unit.path = path


def dest_lot(match, unit):
    """The lot unit's dest is on (None if that processor is gone)."""
    kind, ref = unit.dest
    if kind == "drop":
        return ref if ref in match.roads.drops else None
    proc = match.units.get(ref)
    return proc.home if proc is not None and proc.pid == unit.pid else None


def unload(match, unit, player):
    kind, ref = unit.dest
    if kind == "proc":
        proc = match.units.get(ref)
        if proc is not None and proc.pid == unit.pid:
            put = max(0.0, min(snow_room(proc), unit.load))
            proc.inbox += put
            unit.load -= put
        if unit.load > 1e-6:
            plan_home(match, unit, player, procs=False)
            return
    else:
        player.sell(unit.load)
    unit.load = 0.0
    if unit.back is None:
        unit.trip, unit.dest, unit.path = None, None, []
    else:
        unit.trip, unit.dest = "back", None
        plan_out(match, unit, unit.back)


def haul(ctx, unit, player):
    """Run a hauling machine's trips. True while it is travelling (its kind's step is skipped)."""
    match, world = ctx.match, ctx.world
    speed = MACHINES[unit.mid]["speed"]
    if unit.trip is None:
        full = unit.load >= capacity(player, unit.mid) - 1e-9
        if not full and not (unit.load > 0 and unit.state == "idle"):
            return False
        unit.back = lot_of(world, unit) if full else None
        ctx.release(unit)
        plan_home(match, unit, player)
    if unit.trip == "home":
        unit.state = "hauling"
        lot = dest_lot(match, unit)
        if lot is None:
            plan_home(match, unit, player, procs=False)
        elif travel(world, unit, speed, lot, ctx.dt):
            unload(match, unit, player)
        return True
    if unit.trip == "back":
        unit.state = "moving"
        if unit.back is None or travel(world, unit, speed, unit.back, ctx.dt):
            unit.trip, unit.back, unit.path = None, None, []
        return True
    return False


def cancel_back(unit):
    if unit.trip == "back":
        unit.trip, unit.path = None, []
    unit.back = None


# --- depots ---------------------------------------------------------------------------

def depot_cost(match):
    return round(DEPOT_COST * DEPOT_GROWTH ** len(match.depots))


def build_depot(match, pid):
    """A Snow Depot on the lot pid stands on (paid by pid; every machine unloads there)."""
    p = match.player(pid)
    w = match.world
    x, y = math.floor(p.x), math.floor(p.y)
    i = w.index(x, y)
    if len(match.depots) >= MAX_DEPOTS:
        raise LobbyError(f"The valley has the most depots it can take ({MAX_DEPOTS}).")
    if i is None or not w.reached[i] or w.kind[i] in ("cabin", "site"):
        raise LobbyError("Build depots on cleared ground (not the cabin or ruins).")
    if match.occupied(i):
        raise LobbyError("Something is already built on this spot.")
    for s in match.roads.drops:
        sx, sy = w.xy(s)
        if math.hypot(x - sx, y - sy) < DEPOT_SPACING:
            raise LobbyError(f"Too close to the cabin or another drop point (keep {DEPOT_SPACING} lots apart).")
    p.pay(depot_cost(match))
    match.depots.append(i)
    match.builders[("depot", i)] = pid
    match.roads.add_drop(i)
    match.say(f"{p.name} built a Snow Depot.")


"""Units: every machine a player owns is its own unit on the map. This module is the shared part
(creating units, moving, finding and working targets); each machine kind's behaviour is in
machines.py (STEPS[kind]).

Unit fields: id, pid, mid, x, y (world coordinates, centre of a lot = x + 0.5), target (lot or
None), state ("idle" | "moving" | "working" | "hauling" | "full" | "stalled" | "unlit" | "charging"
for the client), home (lot of a placed machine), per-kind scratch: dir, lot, cd, acc, and
hauling (hauling.py): load (snow carried), trip (None | "home" | "back"), dest, path, back;
processors (factory.py): inbox, outbox.
Moving: straight lines at the machine's speed, WADE_SLOW through lots a person couldn't walk
on (units never get stuck; params.fly ignores that), x the road level's speed on roads
(lot_mult, roads.LEVELS).
Pay: collect() is how machine code is paid for snow it removed: hauling machines (content
"carry") add it to their load (sold when they unload, hauling.py), others are paid at once.
Targets (Ctx.pick): the nearest workable lot passing the kind's filter and not claimed by
another unit, looked for around the unit first (LOCAL lots past its reach); then a full
search from the owner's rally point (a lot, or the owner with "follow"; else the unit), at
most SEARCHES_PER_TICK full searches per tick (the rest wait a tick). A unit further than
RALLY_NEAR from its owner's rally point heads back there first.
work(): dig the target while in reach, else move toward it; leftover work moves on to the next
target in reach within the same tick (big machines clear many lots a second).
Diesel machines stop ("stalled") while their owner's tank is empty.
"""

import math

from . import roads
from .content import MACHINES

LOCAL = 2.5
RALLY_NEAR = 8
MAX_STEPS = 60
SEARCHES_PER_TICK = 25
WADE_SLOW = 0.5


class Unit:
    def __init__(self, uid, pid, mid, x, y, home=None):
        self.id = uid
        self.pid = pid
        self.mid = mid
        self.x = float(x)
        self.y = float(y)
        self.home = home
        self.target = None
        self.state = "idle"
        self.dir = None
        self.lot = None
        self.cd = 0.0
        self.acc = 0.0
        self.load = 0.0
        self.trip = None
        self.dest = None
        self.path = []
        self.back = None
        self.inbox = 0.0
        self.outbox = 0


def add(match, pid, mid, count, x=None, y=None, home=None):
    """Create count units of a machine for pid, at (x, y) (placed machines: exactly there) or
    around the cabin."""
    world = match.world
    jitter = 0 if home is not None else 0.8
    for _ in range(count):
        match.unit_counter += 1
        uid = f"u{match.unit_counter}"
        ux = (world.cx + 0.5 if x is None else x) + match.rng.uniform(-jitter, jitter)
        uy = (world.cy + 0.5 if y is None else y) + match.rng.uniform(-jitter, jitter)
        match.units[uid] = Unit(uid, pid, mid, ux, uy, home)


def remove_player(match, pid):
    for uid in [uid for uid, u in match.units.items() if u.pid == pid]:
        del match.units[uid]


def placed_at(match, i):
    return any(u.home == i for u in match.units.values())


def collect(unit, player, snow):
    """unit removed `snow`: carried in its load if the machine hauls, else paid now."""
    if snow <= 0:
        return
    if MACHINES[unit.mid]["carry"]:
        unit.load += snow
        player.cleared += snow
    else:
        player.earn(snow)


def lot_mult(world, i, fly=False):
    """Speed multiplier for a machine on lot i: roads speed it up, deep snow slows it down."""
    if i is None:
        return 1.0
    if not fly and not world.passable(i):
        return WADE_SLOW
    return roads.unit_speed(world, i)


def rally_point(match, player):
    """Lot coordinates (x, y) where a player's units look for work, or None."""
    if player.rally == "follow":
        return math.floor(player.x), math.floor(player.y)
    if player.rally is not None:
        return match.world.xy(player.rally)
    return None


def move_toward(world, unit, tx, ty, speed, dt, stop=0.0):
    """Move unit toward (tx, ty), stopping `stop` short. Returns the distance left."""
    dist = math.hypot(tx - unit.x, ty - unit.y)
    if dist <= stop:
        return dist
    here = world.index(math.floor(unit.x), math.floor(unit.y))
    step = min(dist - stop, speed * lot_mult(world, here, MACHINES[unit.mid]["params"].get("fly")) * dt)
    unit.x += (tx - unit.x) / dist * step
    unit.y += (ty - unit.y) / dist * step
    return dist - step


class Ctx:
    """One tick's shared bookkeeping: claims and the full-search budget."""

    def __init__(self, match, dt):
        self.match = match
        self.world = match.world
        self.dt = dt
        self.searches = SEARCHES_PER_TICK
        self.claimed = {u.target: u.id for u in match.units.values() if u.target is not None}
        self.rallies = {pid: rally_point(match, p) for pid, p in match.players.items()}
        self.placed = {u.home: u for u in match.units.values() if u.home is not None}

    def release(self, unit):
        if unit.target is not None and self.claimed.get(unit.target) == unit.id:
            del self.claimed[unit.target]
        unit.target = None

    def claim(self, unit, i):
        unit.target = i
        if i is not None:
            self.claimed[i] = unit.id

    def valid(self, unit, ok=None):
        i = unit.target
        return (i is not None and self.world.workable(i) and self.claimed.get(i, unit.id) == unit.id
                and (ok is None or ok(i)))

    def pick(self, unit, reach, ok=None, local_only=False, anywhere=False):
        world = self.world
        rally = None if anywhere else self.rallies.get(unit.pid)
        ux, uy = unit.x - 0.5, unit.y - 0.5
        near_rally = rally is None or math.hypot(ux - rally[0], uy - rally[1]) <= RALLY_NEAR
        if near_rally or local_only:
            local = world.nearest_target(ux, uy, self.claimed, limit=reach + LOCAL, ok=ok)
            if local is not None or local_only:
                return local
        if self.searches <= 0:
            return None
        self.searches -= 1
        fx, fy = rally if rally is not None else (ux, uy)
        found = world.nearest_target(fx, fy, self.claimed, ok=ok)
        return found if found is not None else world.nearest_target(fx, fy, ok=ok)


def work(ctx, unit, player, amount, ok=None, on_dig=None, local_only=False, pay=1.0, anywhere=False):
    """Generic "go to the nearest suitable lot and dig it". amount: snow this tick.
    on_dig(i, removed, cleared) runs after each dig. pay: share of removed snow paid (collected).
    anywhere: ignore the rally point."""
    world, m = ctx.world, MACHINES[unit.mid]
    moved = False
    for _ in range(MAX_STEPS):
        if not ctx.valid(unit, ok):
            ctx.release(unit)
            ctx.claim(unit, ctx.pick(unit, m["reach"], ok, local_only, anywhere))
            if unit.target is None:
                unit.state = "idle"
                return
        tx, ty = world.xy(unit.target)
        tx, ty = tx + 0.5, ty + 0.5
        dist = math.hypot(tx - unit.x, ty - unit.y)
        if dist > m["reach"]:
            if not moved and m["speed"] > 0:
                move_toward(world, unit, tx, ty, m["speed"], ctx.dt, m["reach"] * 0.8)
                unit.state = "moving"
            return
        if not moved and dist > 0.9 and m["speed"] > 0:
            move_toward(world, unit, tx, ty, m["speed"] * 0.5, ctx.dt, 0.8)
        moved = True
        unit.state = "working"
        i = unit.target
        removed, found = world.dig(i, amount)
        if removed:
            collect(unit, player, removed * pay)
            amount -= removed
        if found:
            ctx.match.found(player.id, found, i)
        if on_dig:
            on_dig(i, removed, world.snow[i] <= 0)
        if amount <= 1e-9:
            return


def step(match, dt):
    from .hauling import haul  # both import this module
    from .machines import STEPS
    ctx = Ctx(match, dt)
    blizzard = match.weather.blizzard
    for unit in list(match.units.values()):  # finds can add units (rescued skiers)
        player = match.players.get(unit.pid)
        if player is None or unit.id not in match.units:
            continue
        m = MACHINES[unit.mid]
        if m["diesel"] and player.diesel <= 0:
            unit.state = "stalled"
            continue
        if m["carry"] and haul(ctx, unit, player):
            continue
        rate = m["rate"] * player.machine_mult(unit.mid) * player.work_mult(blizzard)
        STEPS[m["kind"]](ctx, unit, player, rate)


def visible(match, centres, radius):
    """Units within radius (lots, square) of any of the centres, for the client.
    "l": how full a hauler's load is (0-1, only when carrying);
    "f": [input fill 0-1, goods waiting] for processors."""
    from .hauling import capacity
    out = {}
    for u in match.units.values():
        p = match.players.get(u.pid)
        if p is None:
            continue
        if any(abs(u.x - cx) <= radius and abs(u.y - cy) <= radius for cx, cy in centres):
            entry = {"x": round(u.x, 2), "y": round(u.y, 2), "m": u.mid, "p": u.pid, "s": u.state}
            m = MACHINES[u.mid]
            if u.load > 0:
                entry["l"] = round(min(1.0, u.load / max(1e-9, capacity(p, u.mid))), 2)
            if m["kind"] == "processor":
                entry["f"] = [round(u.inbox / max(1e-9, m["params"].get("buffer", 100)), 2), int(u.outbox)]
            out[u.id] = entry
    return out

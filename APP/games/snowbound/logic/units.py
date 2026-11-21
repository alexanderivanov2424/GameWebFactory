"""Units: every machine a player owns is its own worker on the map (helpers run, trucks drive).

A unit works its target lot while the lot's centre is within the machine's reach, else moves
toward it at the machine's speed (WADE_SLOW through lots a person couldn't walk on: units never
get stuck). Work left over after clearing a lot goes to the next lot in reach in the same tick.
Rate: Player.unit_rate x Player.work_mult (frenzy, blizzard). Diesel machines stop while their
owner's tank is empty.
Targets: the nearest workable lot not claimed by another unit, looked for around the unit
first (LOCAL lots past its reach). With nothing near, a full search from the owner's rally
point (a lot, or the owner's character with "follow"; else the unit itself), at most
SEARCHES_PER_TICK full searches per tick (the rest wait a tick). A unit far (> RALLY_NEAR) from
its owner's rally point heads back there first.
Units are created by add(); they start at the cabin (or where something spawned them).
"""

import math

from .content import MACHINES

LOCAL = 2.5
RALLY_NEAR = 8
MAX_STEPS = 60
SEARCHES_PER_TICK = 25
WADE_SLOW = 0.5


class Unit:
    def __init__(self, uid, pid, mid, x, y):
        self.id = uid
        self.pid = pid
        self.mid = mid
        self.x = float(x)
        self.y = float(y)
        self.target = None
        self.state = "idle"  # idle | moving | working | stalled


def add(match, pid, mid, count, x=None, y=None):
    """Create count units of a machine for pid, at (x, y) or around the cabin."""
    world = match.world
    for _ in range(count):
        match.unit_counter += 1
        uid = f"u{match.unit_counter}"
        ux = (world.cx + 0.5 if x is None else x) + match.rng.uniform(-0.8, 0.8)
        uy = (world.cy + 0.5 if y is None else y) + match.rng.uniform(-0.8, 0.8)
        match.units[uid] = Unit(uid, pid, mid, ux, uy)


def remove_player(match, pid):
    for uid in [uid for uid, u in match.units.items() if u.pid == pid]:
        del match.units[uid]


def rally_point(match, player):
    """Lot coordinates (x, y) where pid's units look for work, or None."""
    if player.rally == "follow":
        return math.floor(player.x), math.floor(player.y)
    if player.rally is not None:
        return match.world.xy(player.rally)
    return None


class _Picker:
    def __init__(self, match):
        self.world = match.world
        self.searches = SEARCHES_PER_TICK

    def pick(self, unit, rally, claimed, reach):
        world = self.world
        ux, uy = unit.x - 0.5, unit.y - 0.5  # lot coordinates of the unit's position
        near_rally = rally is None or math.hypot(ux - rally[0], uy - rally[1]) <= RALLY_NEAR
        if near_rally:
            local = world.nearest_target(ux, uy, claimed, limit=reach + LOCAL)
            if local is not None:
                return local
        if self.searches <= 0:
            return None
        self.searches -= 1
        fx, fy = rally if rally is not None else (ux, uy)
        found = world.nearest_target(fx, fy, claimed)
        return found if found is not None else world.nearest_target(fx, fy)


def step(match, dt):
    world = match.world
    blizzard = match.weather.blizzard
    picker = _Picker(match)
    claimed = {u.target: u.id for u in match.units.values() if u.target is not None}
    rallies = {pid: rally_point(match, p) for pid, p in match.players.items()}
    for unit in list(match.units.values()):  # finds can add units (rescued skiers)
        player = match.players.get(unit.pid)
        if player is None:
            continue
        m = MACHINES[unit.mid]
        if m["diesel"] and player.diesel <= 0:
            unit.state = "stalled"
            continue
        work = player.unit_rate(unit.mid) * player.work_mult(blizzard) * dt
        reach = m["reach"]
        moved = False
        for _ in range(MAX_STEPS):
            if unit.target is None or not world.workable(unit.target) or claimed.get(unit.target, unit.id) != unit.id:
                if unit.target is not None and claimed.get(unit.target) == unit.id:
                    del claimed[unit.target]
                unit.target = picker.pick(unit, rallies[unit.pid], claimed, reach)
                if unit.target is None:
                    unit.state = "idle"
                    break
                claimed[unit.target] = unit.id
            tx, ty = world.xy(unit.target)
            tx, ty = tx + 0.5, ty + 0.5
            dist = math.hypot(tx - unit.x, ty - unit.y)
            if dist > reach:
                if moved:
                    break
                here = world.index(math.floor(unit.x), math.floor(unit.y))
                slow = 1 if here is None or world.passable(here) else WADE_SLOW
                step_len = min(dist - reach * 0.8, m["speed"] * slow * dt)
                unit.x += (tx - unit.x) / dist * step_len
                unit.y += (ty - unit.y) / dist * step_len
                unit.state = "moving"
                break
            if not moved and dist > 0.9:
                pull = min(dist - 0.8, m["speed"] * dt * 0.5)
                unit.x += (tx - unit.x) / dist * pull
                unit.y += (ty - unit.y) / dist * pull
            moved = True
            unit.state = "working"
            removed, found = world.dig(unit.target, work)
            if removed:
                player.earn(removed)
                work -= removed
            if found:
                match.found(player.id, found, unit.target)
            if work <= 1e-9:
                break


def visible(match, centres, radius):
    """Units within radius (lots, square) of any of the centres, for the client."""
    out = {}
    for u in match.units.values():
        if u.pid not in match.players:
            continue
        if any(abs(u.x - cx) <= radius and abs(u.y - cy) <= radius for cx, cy in centres):
            out[u.id] = {"x": round(u.x, 2), "y": round(u.y, 2), "m": u.mid, "p": u.pid, "s": u.state}
    return out

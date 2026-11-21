"""Machine crews: every player has one crew per machine kind they own, drawn as one vehicle.

A crew's rate is all that player's machines of that kind together (Player.machine_rate times
Player.work_mult). Each tick it works its target lot if the lot is within the machine's reach,
else drives toward it at the machine's speed. Work left over after clearing a lot moves on to
the next lot in reach in the same tick, so big machines clear many lots a second.
Targets: the nearest workable lot (world.targets) not already claimed by another crew: first
around the crew, then (if the player set a focus) the lot nearest the focus, else the nearest
anywhere. Diesel machines stop while their owner's tank is empty.
"""

import math

from .content import MACHINES

LOCAL = 2.5          # lots around a crew searched before a full search
FOCUS_NEAR = 8       # a crew this close to its owner's focus keeps working locally
MAX_STEPS = 60       # lots one crew may finish in one tick


class Crew:
    def __init__(self, pid, mid, x, y):
        self.pid = pid
        self.mid = mid
        self.x = float(x)
        self.y = float(y)
        self.target = None
        self.state = "idle"  # idle | driving | working | stalled

    @property
    def key(self):
        return f"{self.pid}:{self.mid}"


def _pick(world, crew, player, claimed, reach):
    skip = claimed
    if player.focus is not None:
        fx, fy = world.xy(player.focus)
        if math.hypot(crew.x - fx, crew.y - fy) <= FOCUS_NEAR:
            local = world.nearest_target(crew.x, crew.y, skip, limit=reach + LOCAL)
            if local is not None:
                return local
        return _first(world.nearest_target(fx, fy, skip), lambda: world.nearest_target(fx, fy))
    local = world.nearest_target(crew.x, crew.y, skip, limit=reach + LOCAL)
    if local is not None:
        return local
    return _first(world.nearest_target(crew.x, crew.y, skip), lambda: world.nearest_target(crew.x, crew.y))


def _first(found, fallback):
    """found unless None (lot 0 is a valid index), else fallback()."""
    return found if found is not None else fallback()


def step(match, dt):
    world = match.world
    blizzard = match.weather.blizzard
    crews = match.crews
    for player in match.players.values():
        for mid, n in player.owned.items():
            if n and f"{player.id}:{mid}" not in crews:
                crews[f"{player.id}:{mid}"] = Crew(player.id, mid, world.cx, world.cy)
    claimed = {c.target: c.key for c in crews.values() if c.target is not None}
    for crew in crews.values():
        player = match.players.get(crew.pid)
        if player is None:
            continue
        m = MACHINES[crew.mid]
        if m["diesel"] and player.diesel <= 0:
            crew.state = "stalled"
            continue
        work = player.machine_rate(crew.mid) * player.work_mult(blizzard) * dt
        reach = m["reach"]
        moved = False
        for _ in range(MAX_STEPS):
            if crew.target is None or not world.workable(crew.target) or claimed.get(crew.target, crew.key) != crew.key:
                if crew.target is not None and claimed.get(crew.target) == crew.key:
                    del claimed[crew.target]
                crew.target = _pick(world, crew, player, claimed, reach)
                if crew.target is None:
                    crew.state = "idle"
                    break
                claimed[crew.target] = crew.key
            tx, ty = world.xy(crew.target)
            dist = math.hypot(tx - crew.x, ty - crew.y)
            if dist > reach:
                if moved:
                    break
                step_len = min(dist - reach * 0.8, m["speed"] * dt)
                crew.x += (tx - crew.x) / dist * step_len
                crew.y += (ty - crew.y) / dist * step_len
                crew.state = "driving"
                break
            if not moved and dist > 0.6:
                pull = min(dist - 0.5, m["speed"] * dt * 0.5)
                crew.x += (tx - crew.x) / dist * pull
                crew.y += (ty - crew.y) / dist * pull
            moved = True
            crew.state = "working"
            removed, found = world.dig(crew.target, work)
            if removed:
                player.earn(removed)
                work -= removed
            if found:
                match.found(player.id, found, crew.target)
            if work <= 1e-9:
                break


def remove_player(match, pid):
    for key in [k for k, c in match.crews.items() if c.pid == pid]:
        del match.crews[key]


def public(match):
    return {c.key: {"x": round(c.x, 2), "y": round(c.y, 2), "m": c.mid, "p": c.pid,
                    "n": match.players[c.pid].owned[c.mid], "s": c.state}
            for c in match.crews.values() if c.pid in match.players}

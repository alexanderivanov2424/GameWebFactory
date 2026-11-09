"""Colonists ("dupes"): spawning, needs, health, death and walking along a path. What a colonist
decides to do is in chores.py.

Dupe fields others read or write: id ("d1"), name, x, y (floats in cell units; the standing cell is
(round(x), round(y)), see cx/cy), breath 0-100, kcal 0-4000, bladder 0-100, stress 0-100,
health 0-100, stamina 0-100 (falls while awake, rises asleep), asleep (bool), schedule ("1"-"3"),
germs (float), sick (seconds left, 0 = healthy), needs_wash, carry (None or
{"el", "kg", "temp", "germs"}), task (short text), dead, death ("suffocated", "starved",
"overheated", "froze").
Internal: path (cell indexes still to walk), stress_break (seconds of break left), germ_time.

    spawn(match, count, x, y) -> [Dupe]
    update_needs(match, d, dt)       breath, food, bladder, temperature, stress, germs, health, death
    advance(match, d, dt) -> bool    walk along d.path; False when the next cell is no longer walkable
    fall(match, d, dt)               gravity for a colonist that stands in mid-air with no path
    unstick(match, d) -> bool        a colonist inside solid/tile moves to the nearest open cell
    supported(match, d) -> bool      not centred in mid-air (a standable cell, or between cells)
"""

import math

from . import content, nav

NAMES = ["Ada", "Bram", "Cleo", "Dov", "Edda", "Finn", "Gwen", "Hugo", "Iris", "Jory",
         "Kira", "Lars", "Mira", "Nils", "Odessa", "Pax", "Quinn", "Rue", "Sven", "Tove"]
WALK_SPEED = 4.0
LADDER_SPEED = 3.0
FALL_SPEED = 8.0
BREATH_USE = 0.05      # kg of gas per s (half of real life, so a start room lasts a few cycles)
BREATH_MIN = 0.05      # kg in the cell to breathe it
EXHALE = 0.002         # kg carbon dioxide per s
GERMS_SICK = 15000
KCAL_MAX = 4000
STAMINA_CYCLES = 1.2   # cycles of being awake from full stamina to 0


class Dupe:
    def __init__(self, did, name, x, y, bladder):
        self.id, self.name = did, name
        self.x, self.y = float(x), float(y)
        self.breath, self.kcal, self.bladder = 100.0, 3000.0, bladder
        self.stress, self.health, self.germs = 0.0, 100.0, 0.0
        self.stamina, self.asleep, self.schedule = 100.0, False, "1"
        self.sick = 0.0
        self.needs_wash = False
        self.carry = None
        self.task = "Idle"
        self.dead = False
        self.death = ""
        self.path = []
        self.stress_break = 0.0
        self.warned = set()  # log warnings already given this episode
        self.germ_time = 0.0
        self.last_hurt = "suffocated"

    @property
    def cx(self):
        return math.floor(self.x + 0.5)

    @property
    def cy(self):
        return math.floor(self.y + 0.5)

    def cell(self, world):
        return world.idx(self.cx, self.cy)

    def centered(self):
        return abs(self.x - self.cx) < 0.01 and abs(self.y - self.cy) < 0.01


def spawn(match, count, x, y):
    names = list(NAMES)
    match.rng.shuffle(names)
    out = []
    for _ in range(count):
        seq = getattr(match, "_dupe_seq", 0) + 1
        match._dupe_seq = seq
        name = names[(seq - 1) % len(names)]
        if seq > len(names):
            name += f" {seq // len(names) + 1}"
        d = Dupe(f"d{seq}", name, x, y, match.rng.uniform(0, 30))
        match.dupes[d.id] = d
        out.append(d)
    return out


def breathable_at(world, i, minimum=BREATH_MIN):
    e = world.el[i]
    return (content.PHASE[e] == "gas" and content.ELEMENTS[content.ELEMENT_IDS[e]]["breathable"]
            and world.mass[i] >= minimum)


def _warn(match, d, kind, active, text):
    """Log text once per episode of `kind`; the episode ends when `active` turns false."""
    if not active:
        d.warned.discard(kind)
    elif kind not in d.warned:
        d.warned.add(kind)
        match.log(f"{d.name} {text}")


def update_needs(match, d, dt):
    if d.dead:
        return
    world = match.world
    i = d.cell(world) if world.inside(d.cx, d.cy) else None
    if i is None:
        return
    hurt = []
    sick = d.sick > 0
    # breath
    if breathable_at(world, i):
        eid = world.element_id(i)
        _, kg, _, germs = world.take(i, [eid], BREATH_USE * dt)
        if eid == "polluted_oxygen":
            d.germs += germs
        d.breath = min(100.0, d.breath + 25.0 * dt)
        world.release(d.cx, d.cy, "carbon_dioxide", EXHALE * dt, 37.0)
    else:
        d.breath = max(0.0, d.breath - dt)
        if d.breath <= 0:
            d.health -= 10.0 * dt
            hurt.append("suffocated")
    if not d.asleep:
        d.stamina = max(0.0, d.stamina - 100.0 / (STAMINA_CYCLES * match.cycle_length) * dt)
    # food and bladder
    d.kcal -= 1000.0 / 600.0 * dt * (1.5 if sick else 1.0)
    if d.kcal <= 0:
        d.kcal = 0.0
        d.health -= 0.2 * dt
        hurt.append("starved")
    d.bladder = min(100.0, d.bladder + 100.0 / 600.0 * dt)
    # temperature (the temperature of vacuum is meaningless)
    cold_or_hot = False
    if not world.is_vacuum(i):
        t = world.temp[i]
        if t > 60:
            d.health -= 2.0 * dt
            hurt.append("overheated")
        elif t < -15:
            d.health -= 2.0 * dt
            hurt.append("froze")
        cold_or_hot = not 5 <= t <= 35
    # stress
    delta = -0.01 * world.decor[i] - 0.01
    if sick:
        delta += 0.03
    if d.kcal < 500:
        delta += 0.03
    if cold_or_hot:
        delta += 0.02
    if match.schedules.block_for(d) == "d":
        delta -= 0.02       # downtime: stress recovers faster
    d.stress = max(0.0, min(100.0, d.stress + delta * dt))
    if d.stress_break > 0:
        d.stress_break -= dt
        if d.stress_break <= 0:
            d.stress_break, d.stress = 0.0, 60.0
    elif d.stress >= 100:
        d.stress_break = 30.0
    # germs and sickness
    d.germs *= 0.5 ** (dt / 120.0)
    if d.germs > GERMS_SICK:
        d.germ_time += dt
        if d.germ_time >= 30:
            d.sick, d.germ_time = 600.0, 0.0
    if d.sick > 0:
        d.sick = max(0.0, d.sick - dt)
    _warn(match, d, "breath", d.breath <= 0, "is suffocating!")
    _warn(match, d, "hungry", d.kcal < 500, "is very hungry.")
    _warn(match, d, "sick", d.sick > 0, "got sick.")
    _warn(match, d, "stress", d.stress_break > 0, "is having a stress break.")
    # health
    if hurt:
        d.last_hurt = hurt[0]
    else:
        d.health = min(100.0, d.health + 0.2 * dt)
    if d.health <= 0:
        d.health, d.dead, d.death = 0.0, True, d.last_hurt


def advance(match, d, dt):
    """Walk along d.path. False when the next cell can't be entered any more (re-path)."""
    world = match.world
    while d.path and dt > 1e-9:
        j = d.path[0]
        if not nav.walkable(world, j) or not _footing(world, d, j):
            return False
        tx, ty = j % world.w, j // world.w
        here = d.cell(world)
        ladder = world.ladder[j] or (world.inside(d.cx, d.cy) and world.ladder[here])
        speed = LADDER_SPEED if ladder else WALK_SPEED
        dx, dy = tx - d.x, ty - d.y
        dist = math.hypot(dx, dy)
        step = speed * dt
        if dist <= step:
            d.x, d.y = float(tx), float(ty)
            d.path.pop(0)
            dt -= dist / speed
        else:
            d.x += dx / dist * step
            d.y += dy / dist * step
            dt = 0
    return True


def fall(match, d, dt):
    world = match.world
    if d.path or not world.inside(d.cx, d.cy):
        return
    x = d.cx
    if abs(d.x - x) > 0.01:      # settle sideways first
        d.x = float(x)
    i = d.cell(world)
    if not nav._standable(world, i, d.cy) and d.cy + 1 < world.h and nav.walkable(world, i + world.w):
        d.y = min(d.y + FALL_SPEED * dt, float(d.cy + 1))


def _footing(world, d, j):
    """False when the colonist hangs in mid-air (its ladder or floor is gone) and the next path
    cell isn't a fall or a step up from it: the path is stale."""
    if not d.centered() or not world.inside(d.cx, d.cy):
        return True
    here = d.cell(world)
    if nav._standable(world, here, d.cy):
        return True
    if j == here + world.w:
        return True
    return j // world.w == d.cy and nav._standable(world, j, d.cy) \
        and nav._standable(world, here + world.w, d.cy + 1)


def supported(match, d):
    world = match.world
    if not world.inside(d.cx, d.cy):
        return True
    return not d.centered() or nav._standable(world, d.cell(world), d.cy)


def unstick(match, d):
    """Move a colonist that is inside solid rock or a tile to the nearest open cell."""
    world = match.world
    if not world.inside(d.cx, d.cy):
        return False
    start = d.cell(world)
    if nav.walkable(world, start):
        return False
    seen, level = {start}, [start]
    while level:
        found = [i for i in level if nav.walkable(world, i)]
        if found:
            found.sort(key=lambda i: (not nav._standable(world, i, i // world.w), i))
            d.x, d.y = float(found[0] % world.w), float(found[0] // world.w)
            d.path = []
            return True
        nxt = []
        for i in level:
            for j in world.nbrs[i]:
                if j not in seen:
                    seen.add(j)
                    nxt.append(j)
        level = nxt
    return False

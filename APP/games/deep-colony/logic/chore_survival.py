"""Survival chores: air, food, toilet (or the floor), washing, and sleep. Chosen before any job.

    urgent(match, d) -> bool             a survival need is pressing (jobs and sleep get interrupted)
    pick(match, d, dist) -> Chore|None   the chore for the most pressing need that can be met
    rests(match, d) -> bool              not a work block, or out of stamina: jobs stop
    pick_sleep(match, d, dist) -> Chore|None
        sleep: in a sleep block go to the nearest free reachable bed (building with d["bed"], one per
        colonist) and sleep there (stamina +100 per 0.25 cycle, stress down); with none, sleep where
        standing at half the rate with stress rising. Stamina 0 at any time: sleep on the spot until 30.
        The chore ends when the block stops being "s" (a forced sleep also needs stamina 30).
"""

from . import content, dupes, machines, nav
from .chore_common import (Chore, STORAGE_KINDS, best_goal, claim_live, ctx, failing, is_food,
                           reach_goals, store_free, timed, touch)

KCAL_MAX = dupes.KCAL_MAX


def urgent(match, d):
    world = match.world
    if d.breath < 60 and not dupes.breathable_at(world, d.cell(world)):
        return True
    return d.kcal < 1500 or d.bladder >= 100


def pick(match, d, dist):
    world = match.world
    cell = d.cell(world)
    if d.breath < 60 and not dupes.breathable_at(world, cell) and not failing(match, ("air",)):
        best = None
        for i, n in dist.items():
            if dupes.breathable_at(world, i, 0.5) and (best is None or n < best[0]):
                best = (n, i)
        if best:
            return Chore("air", ("air",), (), _air(best[1]))
    if d.kcal < 1500 and not failing(match, ("eat",)):
        src = _food_source(match, dist)
        if src:
            sb = src[1] if src[0] == "store" else None
            return Chore("eat", ("eat",), [("building", sb.id)] if sb else (), _eat(match, d, src))
    if d.bladder >= 100 and not failing(match, ("toilet",)):
        best = None
        for b in match.buildings:
            if b.built and b.d["toilet"] and machines.toilet_usable(match, b):
                g = best_goal(dist, reach_goals(world, b))
                if g and (best is None or g[0] < best[0]):
                    best = (g[0], b)
        if best:
            return Chore("toilet", ("toilet",), [("building", best[1].id)], _toilet(match, d, best[1]))
        return Chore("pee", ("pee",), (), _pee(match, d))
    if d.needs_wash and not failing(match, ("wash",)):
        best = None
        for b in match.buildings.of_kind("wash_basin"):
            if machines.basin_usable(match, b):
                g = best_goal(dist, reach_goals(world, b))
                if g and (best is None or g[0] < best[0]):
                    best = (g[0], b)
        if best:
            return Chore("wash", ("wash",), [("building", best[1].id)], _wash(match, d, best[1]))
    return None


def rests(match, d):
    return match.schedules.block_for(d) != "w" or d.stamina <= 0


def pick_sleep(match, d, dist):
    block = match.schedules.block_for(d)
    forced = d.stamina <= 0
    if block != "s" and not forced:
        return None
    world = match.world
    if not forced:
        c = ctx(match)
        best = None
        for b in match.buildings:
            if not (b.built and b.d["bed"]) or b.deconstruct or failing(match, ("sleep", b.id)):
                continue
            owner = c.claims.get(("bed", b.id))
            if owner and owner != d.id and claim_live(match, owner):
                continue
            goals = {world.idx(x, y) for x, y in b.cells() if nav.standable(world, x, y)} \
                or reach_goals(world, b)
            g = best_goal(dist, goals)
            if g and (best is None or g[0] < best[0]):
                best = (g[0], b, goals)
        if best:
            b = best[1]
            return Chore("sleep", ("sleep", b.id), [("building", b.id)], _sleep(match, d, best[2], True, False),
                         [("bed", b.id)])
    if failing(match, ("sleep", "floor")):
        return None
    return Chore("sleep", ("sleep", "floor"), (), _sleep(match, d, None, False, forced))


def _sleep(match, d, goals, bed, forced):
    if goals:
        yield ("goto", goals, "Going to bed")
    rate = 100.0 / (0.25 * match.cycle_length) * (1.0 if bed else 0.5)

    def work(dt):
        if match.schedules.block_for(d) != "s" and (not forced or d.stamina >= 30):
            return True
        d.asleep = True
        d.stamina = min(100.0, d.stamina + rate * dt)
        d.stress = max(0.0, min(100.0, d.stress + (-0.03 if bed else 0.1) * dt))
        return False
    try:
        yield ("work", work, "Sleeping")
    finally:
        d.asleep = False


def _air(cell):
    yield ("goto", {cell}, "Seeking air")


def _food_source(match, dist):
    """Nearest reachable food: ("item", Item, el) or ("store", Building, el)."""
    world = match.world
    best = None
    for it in match.items:
        if is_food(it.el) and match.items.available(it) >= 0.01:
            n = dist.get(world.idx(it.x, it.y))
            if n is not None and (best is None or n < best[0]):
                best = (n, ("item", it, it.el))
    for b in match.buildings:
        if not (b.built and b.d["kind"] in STORAGE_KINDS):
            continue
        for el in b.store:
            if is_food(el) and store_free(b, el) >= 0.01:
                g = best_goal(dist, reach_goals(world, b))
                if g and (best is None or g[0] < best[0]):
                    best = (g[0], ("store", b, el))
    return best[1] if best else None


def _release(src, kg):
    kind, obj, el = src
    if kind == "item":
        obj.reserved = max(0.0, obj.reserved - kg)
    else:
        obj.unreserve("out:" + el, kg)


def _eat(match, d, src):
    kind, obj, el = src
    per = content.ELEMENTS[el]["kcal"] or 1.0
    avail = match.items.available(obj) if kind == "item" else store_free(obj, el)
    want = min(avail, max(0.05, (KCAL_MAX - d.kcal) / per))
    if kind == "item":
        obj.reserved += want
    else:
        obj.reserve("out:" + el, want)
    held = want
    try:
        goals = {match.world.idx(obj.x, obj.y)} if kind == "item" else reach_goals(match.world, obj)
        yield ("goto", goals, "Eating")
        yield ("work", timed(d, 3), "Eating")
        _release(src, held)
        held = 0.0
        germs = 0.0
        if kind == "item":
            if obj.id not in match.items.by_id:
                return
            _, kg, _, germs = match.items.take(obj, want)
        else:
            if obj.id not in match.buildings.by_id:
                return
            kg, _, germs = obj.take(el, want)
        d.kcal = min(KCAL_MAX, d.kcal + kg * per)
        d.germs += germs
    finally:
        if held > 0:
            _release(src, held)


def _toilet(match, d, b):
    yield ("goto", reach_goals(match.world, b), "Using toilet")
    work = timed(d, 10)
    used = []

    def fn(dt):
        if b.id not in match.buildings.by_id or not machines.toilet_usable(match, b):
            return True
        if work(dt):
            touch(match, d, b, 1.0)
            machines.use_toilet(match, b, d)
            used.append(1)
            return True
        return False
    yield ("work", fn, "Using toilet")
    if not used:
        yield ("fail",)


def _pee(match, d):
    yield ("work", timed(d, 3), "Relieving themselves")
    match.world.emit(d.cx, d.cy, "polluted_water", 5.0, 37.0, 10000.0)
    d.stress = min(100.0, d.stress + 20.0)
    d.bladder = 0.0


def _wash(match, d, b):
    yield ("goto", reach_goals(match.world, b), "Washing")
    yield ("work", timed(d, 5), "Washing")
    if b.id in match.buildings.by_id and machines.basin_usable(match, b):
        touch(match, d, b, 1.0)
        machines.wash(match, b, d)
    else:
        yield ("fail",)

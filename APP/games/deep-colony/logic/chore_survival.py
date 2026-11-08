"""Survival chores: air, food, toilet (or the floor), washing. Chosen before any job.

    urgent(match, d) -> bool             a survival need is pressing (jobs get interrupted)
    pick(match, d, dist) -> Chore|None   the chore for the most pressing need that can be met
"""

from . import content, dupes
from .chore_common import (Chore, STORAGE_KINDS, best_goal, failing, is_food, mach, reach_goals,
                           store_free, timed)

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
            if b.built and b.d["toilet"] and mach("toilet_usable", match, b, default=False):
                g = best_goal(dist, reach_goals(world, b))
                if g and (best is None or g[0] < best[0]):
                    best = (g[0], b)
        if best:
            return Chore("toilet", ("toilet",), [("building", best[1].id)], _toilet(match, d, best[1]))
        return Chore("pee", ("pee",), (), _pee(match, d))
    if d.needs_wash and not failing(match, ("wash",)):
        best = None
        for b in match.buildings.of_kind("wash_basin"):
            if mach("basin_usable", match, b, default=False):
                g = best_goal(dist, reach_goals(world, b))
                if g and (best is None or g[0] < best[0]):
                    best = (g[0], b)
        if best:
            return Chore("wash", ("wash",), [("building", best[1].id)], _wash(match, d, best[1]))
    return None


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
            kg = min(want, obj.store.get(el, 0.0))
            left = obj.store.get(el, 0.0) - kg
            if left > 0.001:
                obj.store[el] = left
            else:
                obj.store.pop(el, None)
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
        if b.id not in match.buildings.by_id or not mach("toilet_usable", match, b, default=False):
            return True
        if work(dt):
            mach("use_toilet", match, b, d)
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
    if b.id in match.buildings.by_id and mach("basin_usable", match, b, default=False):
        mach("wash", match, b, d)
    else:
        yield ("fail",)

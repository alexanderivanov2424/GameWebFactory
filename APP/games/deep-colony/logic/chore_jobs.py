"""Job chores at buildings and rock: operate, build, dig, deconstruct, harvest, empty.

    add_candidates(match, d, c, dist, out)   append (-priority, distance, n, make) for each job the
                                             colonist could take; make() builds the Chore
"""

from . import content, machines, orders
from .chore_common import (Chore, best_goal, dig_goals, failing, reach_goals, speed, timed)


def add_candidates(match, d, c, dist, out):
    world = match.world

    def add(prio, dist_to, make):
        out.append((-prio, dist_to, len(out), make))

    for b in match.buildings:
        if not b.built:
            if b.materials_ready() and not failing(match, ("build", b.id)):
                g = best_goal(dist, reach_goals(world, b))
                if g:
                    add(b.prio, g[0], lambda b=b: Chore("build", ("build", b.id), [("building", b.id)],
                                                       _build(match, d, b)))
            continue
        if b.deconstruct:
            if not failing(match, ("decon", b.id)):
                g = best_goal(dist, reach_goals(world, b))
                if g:
                    add(b.prio, g[0], lambda b=b: Chore("decon", ("decon", b.id), [("building", b.id)],
                                                       _decon(match, d, b)))
            continue
        if not b.enabled:
            continue
        if b.d["operated"] and ("op", b.id) not in c.claims and not failing(match, ("op", b.id)) \
                and machines.wants_operator(match, b):
            cells = {world.idx(x, y) for x, y in b.cells()}
            g = best_goal(dist, cells) or best_goal(dist, reach_goals(world, b))
            if g:
                add(b.prio, g[0], lambda b=b, goals=cells | reach_goals(world, b):
                    Chore("operate", ("op", b.id), [("building", b.id)], _operate(match, d, b, goals),
                          [("op", b.id)]))
        if machines.harvest_ready(b) and not failing(match, ("harvest", b.id)):
            g = best_goal(dist, reach_goals(world, b))
            if g:
                add(b.prio, g[0], lambda b=b: Chore("harvest", ("harvest", b.id), [("building", b.id)],
                                                   _simple(match, d, b, 5, "harvest")))
        if machines.needs_emptying(b) and not failing(match, ("empty", b.id)):
            g = best_goal(dist, reach_goals(world, b))
            if g:
                add(b.prio, g[0], lambda b=b: Chore("empty", ("empty", b.id), [("building", b.id)],
                                                   _simple(match, d, b, 3, "empty")))
    for i, order in list(match.digs.items()):
        if not world.is_solid(i):
            del match.digs[i]
            continue
        if order["claimed"] and order["claimed"] != d.id or failing(match, ("dig", i)):
            continue
        g = best_goal(dist, dig_goals(world, i))
        if g:
            add(order["prio"], g[0], lambda i=i: Chore("dig", ("dig", i), [("dig", i)], _dig(match, d, i)))


def _name(b):
    return b.d["name"]


def _build(match, d, b):
    yield ("goto", reach_goals(match.world, b), f"Building {_name(b)}")

    def work(dt):
        if b.id not in match.buildings.by_id or b.built or not b.materials_ready():
            return True
        b.progress += dt * speed(d) / max(1.0, b.d["buildTime"])
        if b.progress >= 1:
            orders.finish_build(match, b)
            return True
        return False
    yield ("work", work, f"Building {_name(b)}")


def _decon(match, d, b):
    yield ("goto", reach_goals(match.world, b), f"Deconstructing {_name(b)}")
    total = max(0.5, b.d["buildTime"] * orders.DECON_TIME)

    def work(dt):
        if b.id not in match.buildings.by_id or not b.deconstruct:
            return True
        b.progress += dt * speed(d) / total
        if b.progress >= 1:
            orders.finish_deconstruct(match, b)
            return True
        return False
    yield ("work", work, f"Deconstructing {_name(b)}")


def _operate(match, d, b, goals):
    yield ("goto", goals, f"Operating {_name(b)}")

    def work(dt):
        if b.id not in match.buildings.by_id or not b.built or not b.enabled \
                or not machines.wants_operator(match, b):
            return True
        machines.operate(match, b, d, dt)
        return False
    yield ("work", work, f"Operating {_name(b)}")


def _simple(match, d, b, seconds, what):
    yield ("goto", reach_goals(match.world, b), f"{what.capitalize()} {_name(b)}")
    yield ("work", timed(d, seconds), f"{what.capitalize()} {_name(b)}")
    if b.id in match.buildings.by_id:
        (machines.empty if what == "empty" else machines.harvest)(match, b)


def _dig(match, d, i):
    world = match.world
    order = match.digs.get(i)
    if order is None or (order["claimed"] and order["claimed"] != d.id):
        return
    order["claimed"] = d.id
    try:
        name = content.ELEMENTS[world.element_id(i)]["name"]
        yield ("goto", dig_goals(world, i), f"Digging {name}")

        def work(dt):
            cur = match.digs.get(i)
            if cur is None or not world.is_solid(i):
                match.digs.pop(i, None)
                return True
            hardness = content.ELEMENTS[world.element_id(i)]["hardness"]
            cur["progress"] += dt * speed(d) / max(0.25, orders.DIG_TIME * hardness)
            if cur["progress"] >= 1:
                orders.finish_dig(match, i)
                return True
            return False
        yield ("work", work, f"Digging {name}")
    finally:
        cur = match.digs.get(i)
        if cur is not None and cur["claimed"] == d.id:
            cur["claimed"] = ""

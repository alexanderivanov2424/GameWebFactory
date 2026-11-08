"""Logistics chores: supply (bring materials/inputs to sites and machines) and haul (debris into
storage). Reservations: Item.reserved on debris, Building.reserve("out:<element>") on a store being
emptied, Building.reserve(key) on the target; all released when the chore ends.

    add_candidates(match, d, c, dist, out)   same contract as chore_jobs.add_candidates
"""

from . import content
from .chore_common import (CARRY_MAX, Chore, STORAGE_KINDS, best_goal, failing, is_food, reach_goals,
                           storage_room, store_free, take_carry)


def _sources(match, dist):
    """Everything that can be picked up and is reachable: [(distance, ("item"|"store", obj), el, kg)]."""
    world = match.world
    out = []
    for it in match.items:
        kg = match.items.available(it)
        n = dist.get(world.idx(it.x, it.y))
        if kg >= 0.01 and n is not None:
            out.append((n, ("item", it), it.el, kg))
    for sb in match.buildings.of_kind("storage"):
        if not sb.store:
            continue
        g = best_goal(dist, reach_goals(world, sb))
        if g:
            for el in sb.store:
                kg = store_free(sb, el)
                if kg >= 0.01:
                    out.append((g[0], ("store", sb), el, kg))
    return out


def add_candidates(match, d, c, dist, out):
    world = match.world
    sources = _sources(match, dist)

    def add(prio, dist_to, make):
        out.append((-prio, dist_to, len(out), make))

    for tb in match.buildings:
        needs = tb.site_needs() if not tb.built else tb.supply_needs()
        if not needs or tb.deconstruct and tb.built:
            continue
        if not best_goal(dist, reach_goals(world, tb)):
            continue
        for key, need in needs.items():
            if failing(match, ("supply", tb.id, key)):
                continue
            best = None
            for n, src, el, kg in sources:
                if src[1] is tb or not content.matches(el, key):
                    continue
                if best is None or n < best[0]:
                    best = (n, src, el, kg)
            if best:
                n, src, el, kg = best
                take = min(need, kg, CARRY_MAX)
                targets = [("building", tb.id)] + ([("building", src[1].id)] if src[0] == "store" else [])
                add(tb.prio, n, lambda tb=tb, key=key, take=take, src=src, el=el, targets=targets:
                    Chore("supply", ("supply", tb.id, key), targets,
                          _supply(match, d, tb, key, take, src, el)))
    _add_haul(match, d, dist, sources, add)


def _add_haul(match, d, dist, sources, add):
    world = match.world
    stores = [(sb, best_goal(dist, reach_goals(world, sb))) for sb in match.buildings.of_kind(*STORAGE_KINDS)]
    stores = [(sb, g[0]) for sb, g in stores if g]
    if not stores:
        return
    swept = (s for s in sources if s[1][0] == "item" and s[1][1].sweep)
    for n, src, el, kg in sorted(swept, key=lambda s: (-s[1][1].sweep["prio"], s[0])):
        it = src[1]
        here = match.buildings.at(it.x, it.y)
        if here is not None and here.built and here.d["kind"] in STORAGE_KINDS:
            continue
        if not it.sweep or failing(match, ("haul", it.id)):
            continue
        pick = None
        for sb, sn in stores:
            if not sb.accepts_element(el) or storage_room(sb, el) < 0.01:
                continue
            rank = (0 if is_food(el) and sb.d["kind"] == "ration_box" else 1, sn)
            if pick is None or rank < pick[0]:
                pick = (rank, sb)
        if pick is None:
            continue
        sb = pick[1]
        add(it.sweep["prio"], n, lambda it=it, sb=sb, kg=min(kg, CARRY_MAX):
            Chore("haul", ("haul", it.id), [("building", sb.id)], _haul(match, d, it, sb, kg)))
        return


def _supply(match, d, tb, key, kg, src, el):
    kind, obj = src
    if kind == "item":
        obj.reserved += kg
    else:
        obj.reserve("out:" + el, kg)
    tb.reserve(key, kg)
    src_held, target_held = kg, kg
    try:
        goals = {match.world.idx(obj.x, obj.y)} if kind == "item" else reach_goals(match.world, obj)
        yield ("goto", goals, f"Supplying {content.ELEMENTS[el]['name']}")
        got, temp, germs = _pick_up(match, obj, kind, el, kg)
        src_held = 0.0
        if kind == "store":
            obj.unreserve("out:" + el, kg)
        if got < 0.01:
            return
        take_carry(d, el, got, temp, germs)
        yield ("goto", reach_goals(match.world, tb), f"Supplying {content.ELEMENTS[el]['name']}")
        tb.unreserve(key, kg)
        target_held = 0.0
        if tb.id in match.buildings.by_id:
            tb.deliver(el, d.carry["kg"], d.carry["temp"], d.carry["germs"])
            d.carry = None
    finally:
        if src_held > 0:
            if kind == "item":
                obj.reserved = max(0.0, obj.reserved - src_held)
            else:
                obj.unreserve("out:" + el, src_held)
        if target_held > 0:
            tb.unreserve(key, target_held)


def _pick_up(match, obj, kind, el, kg):
    """Take up to kg of el from a debris pile or a storage store: (kg, temp, germs)."""
    if kind == "item":
        if obj.id not in match.items.by_id:
            return 0.0, 20.0, 0.0
        obj.reserved = max(0.0, obj.reserved - kg)
        _, got, temp, germs = match.items.take(obj, kg)
        return got, temp, germs
    if obj.id not in match.buildings.by_id:
        return 0.0, 20.0, 0.0
    return obj.take(el, kg)


def _haul(match, d, it, sb, kg):
    el = it.el
    it.reserved += kg
    held = kg
    try:
        yield ("goto", {match.world.idx(it.x, it.y)}, f"Hauling {content.ELEMENTS[el]['name']}")
        got, temp, germs = _pick_up(match, it, "item", el, kg)
        held = 0.0
        if got < 0.01:
            return
        take_carry(d, el, got, temp, germs)
        yield ("goto", reach_goals(match.world, sb), f"Hauling {content.ELEMENTS[el]['name']}")
        if sb.id in match.buildings.by_id:
            have = d.carry["kg"]
            put = min(have, storage_room(sb, el)) if sb.accepts_element(el) else 0.0
            if put > 0:
                share = d.carry["germs"] * put / have
                sb.deliver(el, put, d.carry["temp"], share)
                d.carry["germs"] -= share
                d.carry["kg"] -= put
                if d.carry["kg"] < 0.01:
                    d.carry = None
    finally:
        if held > 0:
            it.reserved = max(0.0, it.reserved - held)

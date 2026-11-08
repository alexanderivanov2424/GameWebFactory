"""Chores: what every colonist does next, and doing it. Each step, for every colonist: needs
(dupes.update_needs), choose a chore if it has none, run it.

Choosing (chore_survival.py first, then jobs): breath, food, bladder (toilet, else the floor),
washing; then jobs ranked by priority (higher first, haul = 3) and then walking distance:
operate, build, dig, deconstruct, harvest, empty (chore_jobs.py), supply and haul (chore_haul.py).
One BFS per colonist per choose (cached while buildings/digs are unchanged), at most one choose per
0.5 s for an idle colonist. Survival needs interrupt a job (checked every second).
A chore (chore_common.py) is a generator; ending it (done, failed, cancelled) closes it, which
releases its reservations, and drops anything still carried as debris at the colonist's cell.
A chore that fails is remembered for FAIL_MEMORY seconds so it isn't retried every step.

    step(match, dt)
    cancel_for(match, target)    target ("building", bid) | ("dig", i) | ("dupe", did)
"""

from . import chore_haul, chore_jobs, chore_survival, dupes, nav
from .chore_common import FAIL_MEMORY, best_goal, ctx, navmap

CHOOSE_EVERY = 0.5
SURVIVAL_KINDS = ("air", "eat", "toilet", "pee", "wash")


def step(match, dt):
    c = ctx(match)
    world = match.world
    for did in [k for k in c.chores if k not in match.dupes]:
        _end(match, c.chores[did], False)       # colonist removed: release its claims
    for d in list(match.dupes.values()):
        if d.dead:
            _end(match, c.chores.get(d.id), False)
            continue
        if dupes.unstick(match, d):
            _end(match, c.chores.get(d.id), False)
        dupes.update_needs(match, d, dt)
        ch = c.chores.get(d.id)
        if d.dead:
            _end(match, ch, False)
            continue
        if d.stress_break > 0:
            _end(match, ch, False)
            d.task = "Stress break"
            continue
        if ch is not None and ch.kind not in SURVIVAL_KINDS and match.time - c.last_check.get(d.id, 0) >= 1.0:
            c.last_check[d.id] = match.time
            if c.nosurv.get(d.id, 0) <= match.time and chore_survival.urgent(match, d):
                _end(match, ch, False)
                ch = None
        if ch is None and world.inside(d.cx, d.cy):
            if c.next_choose.get(d.id, 0) <= match.time:
                ch = _choose(match, d, c)
                if ch is None:
                    c.next_choose[d.id] = match.time + CHOOSE_EVERY
                    d.task = "Idle"
        if ch is None:
            dupes.fall(match, d, dt)
            continue
        if not d.path and not dupes.supported(match, d):
            dupes.fall(match, d, dt)            # its footing is gone: fall before going on
            continue
        result = _run(match, d, ch, dt)
        if result:
            _end(match, ch, result == "fail")


def cancel_for(match, target):
    c = ctx(match)
    if target[0] == "dupe":
        _end(match, c.chores.get(target[1]), False)
        return
    for ch in list(c.chores.values()):
        if target in ch.targets:
            _end(match, ch, False)


def _end(match, ch, failed):
    if ch is None:
        return
    c = ctx(match)
    d = ch.dupe
    c.chores.pop(d.id, None)
    ch.gen.close()
    for key in ch.claims:
        if c.claims.get(key) == d.id:
            del c.claims[key]
    if failed:
        c.fail[ch.key] = match.time + FAIL_MEMORY
    d.path = []
    if d.carry:
        world = match.world
        x, y = min(max(d.cx, 0), world.w - 1), min(max(d.cy, 0), world.h - 1)
        match.items.add(d.carry["el"], d.carry["kg"], x, y, d.carry["temp"], d.carry["germs"])
        d.carry = None
    d.task = "Idle"


def _choose(match, d, c):
    world = match.world
    cell = d.cell(world)
    dist, _ = navmap(match, cell)
    ch = chore_survival.pick(match, d, dist)
    if ch is None:
        if chore_survival.urgent(match, d):
            c.nosurv[d.id] = match.time + 10.0
        out = []
        chore_jobs.add_candidates(match, d, c, dist, out)
        chore_haul.add_candidates(match, d, c, dist, out)
        if out:
            ch = min(out, key=lambda e: e[:3])[3]()
    if ch is None:
        return None
    ch.dupe = d
    c.chores[d.id] = ch
    for key in ch.claims:
        c.claims[key] = d.id
    return ch


def _run(match, d, ch, dt):
    """Advance a chore. Returns None (going on), "done" or "fail"."""
    world = match.world
    for _ in range(8):
        if ch.cmd is None:
            try:
                ch.cmd = next(ch.gen)
            except StopIteration:
                return "done"
        cmd = ch.cmd
        if cmd[0] == "fail":
            return "fail"
        d.task = cmd[2]
        if cmd[0] == "work":
            if cmd[1](dt):
                ch.cmd = None
                continue
            return None
        goals = cmd[1]
        here = d.cell(world)
        if here in goals and not d.path and d.centered():
            ch.cmd = None
            continue
        if not d.path:
            if here in goals:
                d.path = [here]
            else:
                dist, parent = navmap(match, here)
                g = best_goal(dist, goals)
                if g is None:
                    return "fail"
                d.path = nav.path(world, parent, here, g[1]) or []
        if not dupes.advance(match, d, dt):
            d.path = []
        return None
    return None

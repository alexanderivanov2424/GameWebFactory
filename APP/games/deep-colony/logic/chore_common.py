"""Shared pieces of the chore system (chores.py, chore_survival.py, chore_jobs.py, chore_haul.py).

A chore is a generator that yields commands to the runner in chores.py:
    ("goto", goal_cells, task_text)   walk until standing (centred) on one of the goal cell indexes
    ("work", fn, task_text)           call fn(dt) every step until it returns True
    ("fail",)                         give up (the runner remembers the failure for a while)
Anything a chore reserves is released in its own try/finally: the runner closes the generator when
the chore ends, fails or is cancelled. A carried load that is left over becomes debris.

    Chore(kind, key, targets, gen, claims=())   key = failure-memory key, targets = set of
                                                ("building", id) / ("dig", i) / ("dupe", id) it aims at
    ctx(match) -> Ctx                           per-match state (chores, failures, claims, nav cache)
    claim_live(match, did)                      a claim's colonist is alive and has a chore
    failing(match, key) -> bool                 gave up on this recently
    navmap(match, cell) -> (dist, parent)       cached BFS from a cell
    best_goal(dist, goals) -> (distance, goal) or None
    reach_goals(world, b)                       standable cells within 1 (Chebyshev) of a building cell
    dig_goals(world, i)                         standing cells from which cell i can be dug
    STORAGE_KINDS, store_free(b, el), storage_room(b, el)
    speed(d) / timed(d, seconds)                work speed (0.5 when sick), a fixed-length work fn
    take_carry(d, el, kg, temp, germs)
"""

from . import content, machines, nav

STORAGE_KINDS = ("storage", "ration_box")
FAIL_MEMORY = 5.0     # s a failed chore isn't retried
CARRY_MAX = 200.0     # kg per trip


class Chore:
    __slots__ = ("kind", "key", "targets", "gen", "cmd", "claims", "dupe")

    def __init__(self, kind, key, targets, gen, claims=()):
        self.kind, self.key, self.targets, self.gen = kind, key, set(targets), gen
        self.cmd = None
        self.claims = tuple(claims)
        self.dupe = None


class Ctx:
    def __init__(self):
        self.chores = {}        # colonist id -> Chore
        self.fail = {}          # key -> match.time until which it is skipped
        self.claims = {}        # key -> colonist id (one operator per machine...)
        self.nav_key = None
        self.nav = {}
        self.next_choose = {}   # colonist id -> time
        self.nosurv = {}        # colonist id -> time until which survival preempts are off
        self.last_check = {}


def ctx(match):
    c = getattr(match, "_chore_ctx", None)
    if c is None:
        c = match._chore_ctx = Ctx()
    return c


def claim_live(match, did):
    """The colonist holding a claim is still alive and busy (else the claim is stale)."""
    d = match.dupes.get(did)
    return d is not None and not d.dead and did in ctx(match).chores


def failing(match, key):
    return ctx(match).fail.get(key, 0.0) > match.time


def navmap(match, cell):
    c = ctx(match)
    key = (match.buildings.version, len(match.digs), int(match.time))   # terrain changes: refresh each second
    if c.nav_key != key:
        c.nav_key, c.nav = key, {}
    got = c.nav.get(cell)
    if got is None:
        got = c.nav[cell] = nav.distances(match.world, cell)
    return got


def best_goal(dist, goals):
    best = None
    for g in goals:
        n = dist.get(g)
        if n is not None and (best is None or n < best[0]):
            best = (n, g)
    return best


def reach_goals(world, b):
    out = set()
    for cx, cy in b.cells():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if nav.standable(world, cx + dx, cy + dy):
                    out.add(world.idx(cx + dx, cy + dy))
    return out


def dig_goals(world, i):
    tx, ty = world.xy(i)
    return {world.idx(sx, sy) for sx in range(tx - 1, tx + 2) for sy in range(ty - 1, ty + 3)
            if nav.standable(world, sx, sy)}


def speed(d):
    return 0.5 if d.sick > 0 else 1.0


def timed(d, seconds):
    left = [float(seconds)]

    def work(dt):
        left[0] -= dt * speed(d)
        return left[0] <= 0
    return work


def take_carry(d, el, kg, temp, germs):
    d.carry = {"el": el, "kg": kg, "temp": temp, "germs": germs}


def store_free(b, el):
    """kg of el in a building's store that nobody has claimed to fetch."""
    return b.store.get(el, 0.0) - b.reserved.get("out:" + el, 0.0)


def storage_room(b, el):
    return machines.storage_room(b, el)


def is_food(el):
    return content.ELEMENTS.get(el, {}).get("phase") == "food"

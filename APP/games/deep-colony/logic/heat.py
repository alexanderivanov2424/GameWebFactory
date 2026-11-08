"""Heat: conduction between 4-neighbour cells and phase changes.

    step(world, dt)

Each pair exchanges K * min(conductivity) * (Ta - Tb) kW; tile cells conduct with TILE_COND
(INSUL_COND when insulated) and have a fixed capacity TILE_CAP kJ/°C, using world.temp[i] as
their temperature. Vacuum conducts nothing. An exchange never passes more than half of what
would equalise the pair. Then phase changes (melt, freeze, boil, condense) keep the mass.
"""

from . import content
from .content import COND, INDEX, SHC, VACUUM

K = 1.0
TILE_COND = 1.0
INSUL_COND = 0.001
TILE_CAP = 100 * 0.8

# element index -> list of (above?, threshold, target index)
_TRANS = [[] for _ in content.ELEMENT_IDS]
for _id, _d in content.ELEMENTS.items():
    _t = _TRANS[INDEX[_id]]
    for _key, _above in (("melt", True), ("boil", True), ("freeze", False), ("condense", False)):
        if f"{_key}At" in _d:
            _t.append((_above, _d[f"{_key}At"], INDEX[_d[f"{_key}To"]]))
_TRANS = [t or None for t in _TRANS]


def step(world, dt):
    w, h = world.w, world.h
    el, mass, temp, tile, insul = world.el, world.mass, world.temp, world.tile, world.insul
    n = world.n
    cond = [0.0] * n
    cap = [0.0] * n
    for i in range(n):
        if tile[i]:
            cond[i] = INSUL_COND if insul[i] else TILE_COND
            cap[i] = TILE_CAP
        elif el[i] != VACUUM:
            e = el[i]
            cond[i] = COND[e]
            cap[i] = mass[i] * SHC[e]
    for i in range(n):
        ca = cond[i]
        if ca <= 0:
            continue
        x = i % w
        for j in ((i + 1) if x < w - 1 else -1, i + w):
            if j < 0 or j >= n:
                continue
            cb = cond[j]
            if cb <= 0:
                continue
            d = temp[i] - temp[j]
            if -1e-6 < d < 1e-6:
                continue
            q = K * (ca if ca < cb else cb) * d * dt
            c1, c2 = cap[i], cap[j]
            limit = 0.5 * d * c1 * c2 / (c1 + c2)
            if d > 0:
                if q > limit:
                    q = limit
            elif q < limit:
                q = limit
            temp[i] -= q / c1
            temp[j] += q / c2
    germs = world.germs
    for i in range(n):
        t = _TRANS[el[i]]
        if t is None:
            continue
        T = temp[i]
        for above, th, to in t:
            if (T >= th) if above else (T <= th):
                world.set_cell(i, content.ELEMENT_IDS[to], mass[i], T, germs[i])
                break

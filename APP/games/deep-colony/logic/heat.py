"""Heat: conduction between 4-neighbour cells and phase changes.

    step(world, dt)

Each pair exchanges K * min(conductivity) * (Ta - Tb) kW; tile cells conduct with TILE_COND
(INSUL_COND when insulated) and have a fixed capacity TILE_CAP kJ/°C, using world.temp[i] as
their temperature. Vacuum conducts nothing. An exchange never passes more than half of what
would equalise the pair. Then phase changes (melt, freeze, boil, condense) keep the mass.
Latent heat: with a nonzero <phase>Latent (kJ/kg) a cell past its threshold is held at the
threshold while the excess heat goes into world.latent[i] (+ absorbed when heating, - released
when cooling); at latent * mass the element changes (leftover heat becomes temperature). If the
cell comes back across the threshold first, the buffer is paid back as heat. Latent 0 = instant.
"""

from . import content
from .content import COND, INDEX, SHC, VACUUM

K = 1.0
TILE_COND = 1.0
INSUL_COND = 0.001
TILE_CAP = 100 * 0.8

# element index -> list of (above?, threshold, target index, latent kJ/kg)
_TRANS = [[] for _ in content.ELEMENT_IDS]
for _id, _d in content.ELEMENTS.items():
    _t = _TRANS[INDEX[_id]]
    for _key, _above in (("melt", True), ("boil", True), ("freeze", False), ("condense", False)):
        if f"{_key}At" in _d:
            _t.append((_above, _d[f"{_key}At"], INDEX[_d[f"{_key}To"]], _d.get(f"{_key}Latent", 0)))
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
    germs, latent, latent_el = world.germs, world.latent, world.latent_el
    ids = content.ELEMENT_IDS
    for i in range(n):
        t = _TRANS[el[i]]
        if t is None:
            continue
        e = el[i]
        buf = latent[i]
        if buf and latent_el[i] != e:
            buf = 0.0
        T = temp[i]
        m = mass[i]
        cap_i = m * SHC[e]
        if cap_i <= 0:
            continue
        for above, th, to, lat in t:
            if above:
                if T > th or (lat <= 0 and T >= th):
                    if lat <= 0:
                        world.set_cell(i, ids[to], m, T, germs[i])
                        buf = 0.0
                        break
                    buf += (T - th) * cap_i
                    T = th
                elif buf > 0 and T < th:
                    pay = min(buf, (th - T) * cap_i)
                    buf -= pay
                    T += pay / cap_i
                    if buf < 1e-9:
                        buf = 0.0
                    continue
                else:
                    continue
                done = buf
            else:
                if T < th or (lat <= 0 and T <= th):
                    if lat <= 0:
                        world.set_cell(i, ids[to], m, T, germs[i])
                        buf = 0.0
                        break
                    buf -= (th - T) * cap_i
                    T = th
                elif buf < 0 and T > th:
                    pay = min(-buf, (T - th) * cap_i)
                    buf += pay
                    T -= pay / cap_i
                    if buf > -1e-9:
                        buf = 0.0
                    continue
                else:
                    continue
                done = -buf
            need = lat * m
            if done >= need:
                left = done - need
                world.set_cell(i, ids[to], m, th, germs[i])
                if el[i] == to:
                    temp[i] = th + (left if above else -left) / (m * SHC[to])
                buf = 0.0
                break
        else:
            temp[i] = T
            if buf:
                latent[i], latent_el[i] = buf, e
            elif latent[i]:
                latent[i] = 0.0
            continue

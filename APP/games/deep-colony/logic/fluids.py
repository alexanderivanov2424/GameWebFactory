"""Fluids: gas and liquid movement on the grid.

    step(world, dt)   one update of every gas and liquid cell (match calls it every FLUID_DT)

Gas: same gas evens out with its neighbours, spills into vacuum, a denser gas above a lighter one
swaps down, a gas with over twice the mass swaps sideways into a different gas. Liquid: falls
through gas, pours into liquid below (cap LIQUID_CAP), spreads sideways (piles under
SPREAD_MIN kg stay put); a liquid cell over LIQUID_CAP (pressurised) also pushes up. Nothing
bigger than rounding is deleted: gas pushed out by liquid goes through world.release.
Different liquids never mix. Each cell swaps at most once per step
(`moved` flags) and the scan direction alternates every step so nothing drifts.
"""

from . import content
from .content import DENSITY, PHASE, VACUUM
from .grid import GAS_MIN, LIQUID_MIN

LIQUID_CAP = 1000.0
SPREAD_MIN = 5.0
GAS_SHARE = 0.2      # of the difference per neighbour (same gas)
VACUUM_SHARE = 0.2   # of a gas cell's mass per vacuum neighbour
LIQUID_SHARE = 0.25

_flip = [False]
_GAS = [p == "gas" for p in PHASE]
_LIQ = [p == "liquid" for p in PHASE]
_SOL = [p == "solid" for p in PHASE]


def _swap(world, a, b):
    el, mass, temp, germs = world.el, world.mass, world.temp, world.germs
    el[a], el[b] = el[b], el[a]
    mass[a], mass[b] = mass[b], mass[a]
    temp[a], temp[b] = temp[b], temp[a]
    germs[a], germs[b] = germs[b], germs[a]


def _move_gas(world, i, j, dm):
    """Move dm kg of the gas in i into j (vacuum or the same gas)."""
    mass, temp, germs = world.mass, world.temp, world.germs
    share = dm / mass[i]
    g = germs[i] * share
    if world.el[j] == VACUUM:
        world.el[j] = world.el[i]
        mass[j], temp[j], germs[j] = dm, temp[i], g
    else:
        total = mass[j] + dm
        temp[j] = (temp[j] * mass[j] + temp[i] * dm) / total
        mass[j] = total
        germs[j] += g
    mass[i] -= dm
    germs[i] -= g


def _move_liquid(world, i, j, dm):
    """Move dm kg of liquid i into j (gas/vacuum are replaced, same liquid is added to)."""
    mass, temp, germs, el = world.mass, world.temp, world.germs, world.el
    share = dm / mass[i]
    g = germs[i] * share
    pushed = None
    if el[j] == el[i]:
        total = mass[j] + dm
        temp[j] = (temp[j] * mass[j] + temp[i] * dm) / total
        mass[j] = total
        germs[j] += g
    else:
        old_gas = (content.ELEMENT_IDS[el[j]], mass[j], temp[j], germs[j]) if el[j] != VACUUM else None
        el[j] = el[i]
        mass[j], temp[j], germs[j] = dm, temp[i], g
        world.latent[j] = 0.0
        if old_gas:
            pushed = old_gas
    mass[i] -= dm
    germs[i] -= g
    if mass[i] < LIQUID_MIN:
        el[i], mass[i], germs[i] = VACUUM, 0.0, 0.0
    if pushed:  # the displaced gas is never deleted: placed by pressure or kept pending
        world.release(j % world.w, j // world.w, *pushed)


def step(world, dt):
    if world.pending:
        world.drain_pending()
    w, h = world.w, world.h
    el, mass, tile = world.el, world.mass, world.tile
    nbrs = world.nbrs
    moved = bytearray(world.n)
    _flip[0] = not _flip[0]
    xs = range(w - 1, -1, -1) if _flip[0] else range(w)
    for y in range(h - 1, -1, -1):
        row = y * w
        for x in xs:
            i = row + x
            e = el[i]
            if tile[i] or moved[i]:
                continue
            if _GAS[e]:
                _gas_cell(world, i, e, nbrs[i], moved, w)
            elif _LIQ[e]:
                _liquid_cell(world, i, e, x, y, moved, w, h)


def _gas_cell(world, i, e, ns, moved, w):
    el, mass, tile = world.el, world.mass, world.tile
    for j in ns:
        m = mass[i]
        if el[i] != e or m < GAS_MIN:
            break
        if tile[j]:
            continue
        ej = el[j]
        if ej == e:
            diff = m - mass[j]
            if diff > 0.002:
                _move_gas(world, i, j, diff * GAS_SHARE)
        elif ej == VACUUM:
            dm = m * VACUUM_SHARE
            if dm >= GAS_MIN:
                _move_gas(world, i, j, dm)
        elif _GAS[ej] and not moved[j]:
            if j == i + w:      # j below i: denser gas above sinks
                swap = DENSITY[e] > DENSITY[ej]
            elif j == i - w:
                swap = False    # handled when scanning the cell below
            else:
                swap = m > 2 * mass[j]
            if swap:
                _swap(world, i, j)
                moved[i] = moved[j] = 1
                break
    if el[i] == e and mass[i] < GAS_MIN:
        el[i], mass[i], world.germs[i] = VACUUM, 0.0, 0.0


def _liquid_cell(world, i, e, x, y, moved, w, h):
    el, mass, tile = world.el, world.mass, world.tile
    if y + 1 < h:
        j = i + w
        if not tile[j] and not moved[j]:
            ej = el[j]
            if ej == VACUUM or _GAS[ej]:
                _swap(world, i, j)
                moved[i] = moved[j] = 1
                return
            if ej == e:
                room = LIQUID_CAP - mass[j]
                dm = min(mass[i], room)
                if dm > 0.01:
                    _move_liquid(world, i, j, dm)
                    if el[i] != e:
                        return
    if mass[i] < SPREAD_MIN:
        return
    for j, ok in ((i - 1, x > 0), (i + 1, x < w - 1)):
        if not ok or tile[j] or moved[j] or el[i] != e:
            continue
        ej = el[j]
        if ej == VACUUM or _GAS[ej]:
            dm = mass[i] * LIQUID_SHARE
            if dm >= LIQUID_MIN * 2:
                _move_liquid(world, i, j, dm)
                moved[j] = 1
        elif ej == e:
            diff = mass[i] - mass[j]
            if diff > 1.0:
                _move_liquid(world, i, j, diff * LIQUID_SHARE)
    if y > 0 and mass[i] > LIQUID_CAP and el[i] == e:
        j = i - w
        if not tile[j] and el[j] == e and not moved[j]:
            diff = mass[i] - mass[j]
            if diff > 1.0:
                _move_liquid(world, i, j, diff * LIQUID_SHARE)

"""Germs and decor fields.

    step(world, items, dt, buildings=None)               germ die-off, off-gassing (liquids and debris piles)
    update_decor(world, buildings, items) recompute world.decor
    touch(match, dupe, b, dt)            a colonist working at / using a structure: germs pass both ways
                                          (called by the job and survival chores, not by step)

Germs lose dt/300 of their count per step (3x above 50 °C, 2x more in solid cells). An element
with "offgas" turns rate*dt kg of itself into the offgas element: a liquid cell does it into the
cell above when that is gas or vacuum; a debris pile does it at its own cell. Germs on structures
(b.germs) and on debris piles (item.germs) die off by the same rule (piles by their own temp). Pass buildings=match.buildings to step for the structures.
touch moves TOUCH_RATE*dt of the difference between colonist and structure germs toward each other,
so the total is conserved.
"""

from . import content
from .content import ELEMENTS, INDEX, PHASE, VACUUM

DIE = 1 / 300
TOUCH_RATE = 0.1     # share of the germ difference exchanged per second
HOT = 50.0
OFFGAS_GERMS = 0.3   # share of the converted mass's germs that go into the gas

_OFF = {INDEX[i]: (i, d["offgas"]["element"], d["offgas"]["rate"])
        for i, d in ELEMENTS.items() if "offgas" in d and PHASE[INDEX[i]] == "liquid"}


def step(world, items, dt, buildings=None):
    el, germs, temp, mass, w = world.el, world.germs, world.temp, world.mass, world.w
    base = DIE * dt
    for i, g in enumerate(germs):
        if g > 0:
            e = el[i]
            f = base * (3 if temp[i] > HOT else 1) * (2 if PHASE[e] == "solid" else 1)
            g -= g * f if f < 1 else g
            germs[i] = g if g > 0.01 else 0.0
    if _OFF:
        for i, e in enumerate(el):
            off = _OFF.get(e)
            if off is None or i < w or mass[i] <= 0:
                continue
            up = i - w
            if world.blocks_fluid(up) or PHASE[el[up]] not in ("gas", "vacuum"):
                continue
            eid, gas, rate = off
            _, kg, t, g = world.take(i, (eid,), rate * dt)
            if kg > 0:
                world.emit(up % w, up // w, gas, kg, t, g * OFFGAS_GERMS)
    for b in buildings or ():
        if b.germs > 0:
            b.germs = _decay(b.germs, base, 20.0, True)
    for it in items:
        if it.germs > 0:
            it.germs = _decay(it.germs, base, it.temp, ELEMENTS.get(it.el, {}).get("phase") == "solid")
        d = ELEMENTS.get(it.el)
        if d and "offgas" in d:
            _, kg, t, g = items.take(it, d["offgas"]["rate"] * dt)
            if kg > 0:
                world.emit(it.x, it.y, d["offgas"]["element"], kg, t, g * OFFGAS_GERMS)


def _decay(g, base, temp, solid):
    f = base * (3 if temp > HOT else 1) * (2 if solid else 1)
    g -= g * f if f < 1 else g
    return g if g > 0.01 else 0.0


def touch(match, dupe, b, dt):
    """A colonist works at or uses structure b: germs flow toward equal levels, conserved."""
    move = (dupe.germs - b.germs) * min(1.0, TOUCH_RATE * dt)
    dupe.germs -= move
    b.germs += move


def update_decor(world, buildings, items):
    decor = world.decor
    for i in range(len(decor)):
        decor[i] = 0.0
    w, h = world.w, world.h
    for b in buildings:
        if not b.built:
            continue
        value, r = b.d["decor"]["value"], b.d["decor"]["radius"]
        if not value:
            continue
        cells = list(b.cells())
        x0 = min(c[0] for c in cells) - r
        x1 = max(c[0] for c in cells) + r
        y0 = min(c[1] for c in cells) - r
        y1 = max(c[1] for c in cells) + r
        for y in range(max(0, y0), min(h - 1, y1) + 1):
            for x in range(max(0, x0), min(w - 1, x1) + 1):
                decor[y * w + x] += value
    piles = set()
    for it in items:
        d = ELEMENTS.get(it.el)
        if d and d["decor"]:
            piles.add((it.el, it.x, it.y))
    for el, px, py in piles:
        v = ELEMENTS[el]["decor"]
        for y in range(max(0, py - 1), min(h - 1, py + 1) + 1):
            for x in range(max(0, px - 1), min(w - 1, px + 1) + 1):
                decor[y * w + x] += v

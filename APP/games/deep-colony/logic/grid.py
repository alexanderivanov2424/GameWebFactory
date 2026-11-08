"""World: the cell grid. One element per cell (with mass kg, temperature °C and germs), plus the
flags buildings put on cells. No buildings, colonists or lobby code here.

Coordinates: x to the right, y downward (row 0 is the top). Cell index i = y * w + x.
Flat lists, indexed by i, for speed:
    el[i]     element index (content.ELEMENT_IDS / INDEX; 0 = vacuum)
    mass[i]   kg (0 for vacuum)
    temp[i]   °C (kept for vacuum too, unused)
    germs[i]  germ count (float)
    tile[i]   True while a solid building (tile, insulated tile, door) stands here: gas and liquid
              treat the cell as solid, colonists can stand on it (doors: walk through it)
    door[i]   True for door cells (walkable although tile[i] is set)
    ladder[i] True for ladder cells
    insul[i]  True for insulated tiles (heat barely passes)
    decor[i]  decor value at the cell (germs.update_decor fills it)

Helpers:
    world.blocks_fluid(i)   solid element or tile: gas/liquid can't enter
    world.is_gas(i) / is_liquid(i) / is_solid(i) (element only) / is_open(i) (not solid, not tile)
    world.set_cell(i, element_id, mass, temp, germs=0)
    world.emit(x, y, element_id, kg, temp, germs=0) -> kg placed (see its docstring)
    world.release(x, y, element_id, kg, temp, germs=0)  like emit, but never loses mass: whatever
                            emit can't place waits in world.pending and is retried every
                            fluid step (drain_pending)
    world.drain_pending()   retry pending releases (fluids.step calls it)
    world.take(i, element_ids, kg) -> (element_id, kg, temp, germs) taken from cell i
    world.dig(i) -> (element_id, kg, temp, germs) and leaves vacuum
    world.add_heat(i, kj)  heat (kJ, negative cools) into cell i (or its first non-vacuum neighbour)
    world.neighbours4(i) -> list of indexes (precomputed)
"""

from . import content
from .content import DENSITY, INDEX, PHASE, SHC, VACUUM

GAS_MIN = 0.001      # kg: less than this is vacuum
LIQUID_MIN = 0.05    # kg: less than this disappears
HEAT_MASS_MIN = 0.5  # kg: add_heat treats a lighter cell as this heavy (no absurd spikes)


class World:
    def __init__(self, w, h, fill="vacuum", temp=20.0):
        self.w, self.h = w, h
        n = w * h
        self.n = n
        self.el = [INDEX[fill]] * n
        self.mass = [0.0 if fill == "vacuum" else content.ELEMENTS[fill]["defaultMass"]] * n
        self.temp = [float(temp)] * n
        self.germs = [0.0] * n
        self.tile = [False] * n
        self.door = [False] * n
        self.ladder = [False] * n
        self.insul = [False] * n
        self.decor = [0.0] * n
        self.pending = []  # [x, y, element_id, kg, temp, germs] waiting for room (release)
        self.nbrs = [self._neighbours(i) for i in range(n)]

    # --- geometry -------------------------------------------------------------------------

    def idx(self, x, y):
        return y * self.w + x

    def xy(self, i):
        return i % self.w, i // self.w

    def inside(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def _neighbours(self, i):
        x, y = i % self.w, i // self.w
        return [self.idx(nx, ny) for nx, ny in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1))
                if self.inside(nx, ny)]

    def neighbours4(self, i):
        return self.nbrs[i]

    # --- cell queries ---------------------------------------------------------------------

    def element_id(self, i):
        return content.ELEMENT_IDS[self.el[i]]

    def phase(self, i):
        return PHASE[self.el[i]]

    def is_solid(self, i):
        return PHASE[self.el[i]] == "solid"

    def is_gas(self, i):
        return PHASE[self.el[i]] == "gas"

    def is_liquid(self, i):
        return PHASE[self.el[i]] == "liquid"

    def is_vacuum(self, i):
        return self.el[i] == VACUUM

    def blocks_fluid(self, i):
        return self.tile[i] or PHASE[self.el[i]] == "solid"

    def is_open(self, i):
        """Not solid rock and no tile: gas, liquid or vacuum (doors count as closed here)."""
        return not self.blocks_fluid(i)

    # --- changes --------------------------------------------------------------------------

    def set_cell(self, i, element_id, mass, temp, germs=0.0):
        e = INDEX[element_id]
        phase = PHASE[e]
        if phase == "vacuum" or (phase == "gas" and mass < GAS_MIN) or (phase == "liquid" and mass < LIQUID_MIN):
            self.el[i], self.mass[i], self.germs[i] = VACUUM, 0.0, 0.0
            return
        self.el[i], self.mass[i], self.temp[i], self.germs[i] = e, float(mass), float(temp), float(germs)

    def add_mass(self, i, kg, temp, germs=0.0):
        """Add kg of the cell's own element at temp (mixes temperature by heat capacity)."""
        m = self.mass[i]
        total = m + kg
        if total <= 0:
            return
        self.temp[i] = (self.temp[i] * m + temp * kg) / total
        self.mass[i] = total
        self.germs[i] += germs

    def emit(self, x, y, element_id, kg, temp, germs=0.0):
        """Put kg of a gas or liquid into the world at (x, y). Returns the kg placed.

        Goes into the cell if it holds the same element or vacuum; otherwise into the nearest
        cell (within 2 steps, open cells only) that does; otherwise a liquid displaces the gas
        in the cell (the gas is lost) and a gas is dropped (returns 0). Never into solids/tiles.
        """
        if kg <= 0 or not self.inside(x, y):
            return 0.0
        e = INDEX[element_id]
        start = self.idx(x, y)
        frontier, seen = [start], {start}
        for _ in range(3):
            nxt = []
            for i in frontier:
                if self.blocks_fluid(i):
                    continue
                if self.el[i] == e:
                    self.add_mass(i, kg, temp, germs)
                    return kg
                if self.el[i] == VACUUM:
                    self.set_cell(i, element_id, kg, temp, germs)
                    return kg if self.el[i] == e else 0.0
                for j in self.nbrs[i]:
                    if j not in seen:
                        seen.add(j)
                        nxt.append(j)
            frontier = nxt
        if PHASE[e] == "liquid" and not self.blocks_fluid(start) and PHASE[self.el[start]] == "gas":
            self.set_cell(start, element_id, kg, temp, germs)
            return kg
        return 0.0

    def release(self, x, y, element_id, kg, temp, germs=0.0):
        """Put a gas or liquid into the world without ever losing it (see the module docstring)."""
        placed = self.emit(x, y, element_id, kg, temp, germs)
        left = kg - placed
        if left > 1e-9:
            share = left / kg if kg else 0.0
            self.pending.append([x, y, element_id, left, temp, germs * share])

    def drain_pending(self):
        """Retry everything waiting in pending (keeps what still doesn't fit)."""
        waiting, self.pending = self.pending, []
        for x, y, element_id, kg, temp, germs in waiting:
            self.release(x, y, element_id, kg, temp, germs)

    def take(self, i, element_ids, kg):
        """Take up to kg from cell i if it holds one of element_ids. Returns (id, kg, temp, germs)."""
        e = self.el[i]
        eid = content.ELEMENT_IDS[e]
        if eid not in element_ids or kg <= 0 or self.mass[i] <= 0:
            return None, 0.0, 0.0, 0.0
        got = min(kg, self.mass[i])
        share = got / self.mass[i]
        germs = self.germs[i] * share
        temp = self.temp[i]
        self.mass[i] -= got
        self.germs[i] -= germs
        if self.mass[i] < (GAS_MIN if PHASE[e] == "gas" else LIQUID_MIN):
            self.el[i], self.mass[i], self.germs[i] = VACUUM, 0.0, 0.0
        return eid, got, temp, germs

    def dig(self, i):
        """Remove a solid cell; returns what was there (id, kg, temp, germs) and leaves vacuum."""
        out = (content.ELEMENT_IDS[self.el[i]], self.mass[i], self.temp[i], self.germs[i])
        self.el[i], self.mass[i], self.germs[i] = VACUUM, 0.0, 0.0
        return out

    def heavier(self, a, b):
        """Whether cell a's fluid is denser than cell b's (for layering)."""
        return DENSITY[self.el[a]] > DENSITY[self.el[b]]

    def add_heat(self, i, kj):
        """Add heat (kJ) to cell i; vacuum and tiles pass it to the first neighbour holding matter."""
        for j in [i] + self.nbrs[i]:
            if self.el[j] != VACUUM and not self.tile[j] and self.mass[j] > 0:
                self.temp[j] += kj / (max(self.mass[j], HEAT_MASS_MIN) * SHC[self.el[j]])
                if self.temp[j] < -273:
                    self.temp[j] = -273.0
                return

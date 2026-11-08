"""Deep Colony: fluids, heat, germs, decor and map generation tests (small hand-made worlds).
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_world.py
"""

import random
import unittest
from importlib import import_module

fluids = import_module("games.deep-colony.logic.fluids")
heat = import_module("games.deep-colony.logic.heat")
germs = import_module("games.deep-colony.logic.germs")
mapgen = import_module("games.deep-colony.logic.mapgen")
grid = import_module("games.deep-colony.logic.grid")
match_mod = import_module("games.deep-colony.logic.match")
items_mod = import_module("games.deep-colony.logic.items")

World = grid.World


def total(world, el):
    e = world.el
    return sum(world.mass[i] for i in range(world.n) if world.element_id(i) == el)


class FluidTests(unittest.TestCase):
    def test_gas_spreads_into_vacuum(self):
        w = World(5, 1, "vacuum")
        w.set_cell(0, "oxygen", 2.0, 20)
        for _ in range(10):
            fluids.step(w, 0.5)
        self.assertFalse(w.is_vacuum(2))
        self.assertAlmostEqual(total(w, "oxygen"), 2.0, places=3)

    def test_heavy_gas_sinks_below_light(self):
        w = World(1, 2, "vacuum")
        w.set_cell(0, "carbon_dioxide", 1.5, 20)
        w.set_cell(1, "oxygen", 1.5, 20)
        fluids.step(w, 0.5)
        self.assertEqual(w.element_id(1), "carbon_dioxide")
        self.assertEqual(w.element_id(0), "oxygen")

    def test_liquid_falls_into_gas(self):
        w = World(1, 3, "vacuum")
        w.set_cell(0, "water", 100, 20)
        w.set_cell(1, "oxygen", 1.5, 20)
        w.set_cell(2, "oxygen", 1.5, 20)
        fluids.step(w, 0.5)
        self.assertEqual(w.element_id(1), "water")
        self.assertEqual(w.element_id(0), "oxygen")

    def test_liquid_does_not_enter_blocked_cells(self):
        w = World(3, 2, "vacuum")
        w.set_cell(1, "water", 100, 20)
        w.set_cell(3, "granite", 1000, 20)
        w.tile[5] = True
        w.set_cell(4, "granite", 1000, 20)
        w.set_cell(0, "granite", 1000, 20)
        w.set_cell(2, "granite", 1000, 20)
        for _ in range(5):
            fluids.step(w, 0.5)
        self.assertEqual(w.element_id(1), "water")
        self.assertEqual(w.element_id(4), "granite")
        self.assertTrue(w.is_vacuum(5))

    def test_gas_never_enters_tile(self):
        w = World(2, 1, "vacuum")
        w.set_cell(0, "oxygen", 2.0, 20)
        w.tile[1] = True
        for _ in range(5):
            fluids.step(w, 0.5)
        self.assertTrue(w.is_vacuum(1))


class HeatTests(unittest.TestCase):
    def test_heat_flows_hot_to_cold(self):
        w = World(2, 1, "oxygen")
        w.temp[0], w.temp[1] = 40.0, 20.0
        heat.step(w, 0.5)
        self.assertLess(w.temp[0], 40.0)
        self.assertGreater(w.temp[1], 20.0)

    def test_insulated_tile_barely_passes_heat(self):
        def run(insul):
            w = World(3, 1, "oxygen")
            w.tile[1] = True
            w.insul[1] = insul
            w.temp[0], w.temp[1], w.temp[2] = 60.0, 20.0, 20.0
            for _ in range(20):
                heat.step(w, 0.5)
            return w.temp[2]
        self.assertLess(run(True) - 20.0, (run(False) - 20.0) / 10)

    def test_water_freezes(self):
        w = World(1, 1, "vacuum")
        w.set_cell(0, "water", 100, -5)
        heat.step(w, 0.5)
        self.assertEqual(w.element_id(0), "ice")
        self.assertAlmostEqual(w.mass[0], 100)


class GermTests(unittest.TestCase):
    def test_germs_die_off(self):
        w = World(1, 1, "oxygen")
        w.germs[0] = 1000.0
        for _ in range(100):
            germs.step(w, items_mod.Items(), 0.5)
        self.assertLess(w.germs[0], 1000.0)

    def test_polluted_water_offgasses_up(self):
        w = World(1, 2, "vacuum")
        w.set_cell(1, "polluted_water", 100, 20)
        germs.step(w, items_mod.Items(), 0.5)
        self.assertEqual(w.element_id(0), "polluted_oxygen")
        self.assertLess(w.mass[1], 100)


class DecorTests(unittest.TestCase):
    def test_decor_radius(self):
        m = match_mod.Match.blank(11, 5)
        b = m.buildings.place("sculpture", 5, 2, "", built=True)
        radius = b.d["decor"]["radius"]
        value = b.d["decor"]["value"]
        germs.update_decor(m.world, m.buildings, m.items)
        self.assertEqual(m.world.decor[2 * 11 + 5], value)
        far = 5 + b.d["w"] - 1 + radius + 1
        if far < 11:
            self.assertEqual(m.world.decor[2 * 11 + far], 0)


class MapgenTests(unittest.TestCase):
    def test_start_and_border(self):
        world, (px, py) = mapgen.generate(80, 48, random.Random(5))
        for x in range(world.w):
            self.assertEqual(world.element_id(x), "bedrock")
            self.assertEqual(world.element_id((world.h - 1) * world.w + x), "bedrock")
        for y in range(world.h):
            self.assertEqual(world.element_id(y * world.w), "bedrock")
            self.assertEqual(world.element_id(y * world.w + world.w - 1), "bedrock")
        for y in range(py, py + 3):
            for x in range(px, px + 3):
                self.assertFalse(world.blocks_fluid(world.idx(x, y)))
        for x in range(px, px + 3):
            self.assertTrue(world.is_solid(world.idx(x, py + 3)))

    def test_start_resources_guaranteed(self):
        R = mapgen.ROOM_W, mapgen.ROOM_H
        for size, (w, h) in match_mod.MAP_SIZES.items():
            for seed in range(6):
                world, (px, py) = mapgen.generate(w, h, random.Random(seed))
                cx, cy = w // 2 - R[0] // 2, h // 2 - R[1] // 2
                counts = {}
                for y in range(h):
                    for x in range(w):
                        el = world.element_id(y * w + x)
                        near = cx - 12 <= x <= cx + R[0] + 11 and cy - 12 <= y <= cy + R[1] + 12
                        if near:
                            counts[el] = counts.get(el, 0) + 1
                for el, n in (("algae", 6), ("copper_ore", 6), ("sand", 6), ("dirt", 6), ("water", 4)):
                    self.assertGreaterEqual(counts.get(el, 0), n, (size, seed, el))
                for y in range(py, py + 3):
                    for x in range(px, px + 3):
                        self.assertFalse(world.is_solid(y * w + x))
                for x in range(px, px + 3):
                    self.assertTrue(world.is_solid((py + 3) * w + x))

    def test_deterministic(self):
        a, pa = mapgen.generate(60, 40, random.Random(9))
        b, pb = mapgen.generate(60, 40, random.Random(9))
        self.assertEqual((a.el, a.mass, a.temp, pa), (b.el, b.mass, b.temp, pb))


if __name__ == "__main__":
    unittest.main()

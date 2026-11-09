"""Deep Colony: sweep-gated hauling, storage filters, temperatures and germs through containers.
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_storage.py
"""

import unittest
from importlib import import_module

match_mod = import_module("games.deep-colony.logic.match")
dupes = import_module("games.deep-colony.logic.dupes")
germs = import_module("games.deep-colony.logic.germs")

W, H = 20, 10


def floor_world():
    m = match_mod.Match.blank(W, H, "oxygen")
    for x in range(W):
        for y in (8, 9):
            m.world.set_cell(m.world.idx(x, y), "sandstone", 1000, 20)
    return m


def run(m, seconds, until=None, dt=0.1):
    for _ in range(int(seconds / dt)):
        m.step(dt)
        if until and until():
            return True
    return until() if until else None


SWEEP = {"by": "p1", "prio": 5}


class HaulTests(unittest.TestCase):
    def setUp(self):
        self.m = floor_world()
        dupes.spawn(self.m, 1, 6, 7)

    def test_unswept_debris_is_left_alone(self):
        bin_ = self.m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        self.m.items.add("sandstone", 50, 3, 7)
        run(self.m, 20)
        self.assertEqual(bin_.store.get("sandstone", 0), 0)

    def test_swept_debris_is_hauled_and_the_mark_is_gone(self):
        bin_ = self.m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        self.m.items.add("sandstone", 20, 3, 7).sweep = dict(SWEEP)
        self.assertTrue(run(self.m, 60, until=lambda: bin_.store.get("sandstone", 0) > 19))
        self.assertEqual(len(list(self.m.items)), 0)

    def test_filtered_storage_refuses_and_another_takes_it(self):
        closed = self.m.buildings.place("storage_bin", 8, 7, "p1", built=True)
        closed.filter = {"oxygen"}
        open_ = self.m.buildings.place("storage_bin", 14, 7, "p1", built=True)
        self.m.items.add("sandstone", 20, 3, 7).sweep = dict(SWEEP)
        self.assertTrue(run(self.m, 80, until=lambda: open_.store.get("sandstone", 0) > 19))
        self.assertEqual(closed.store.get("sandstone", 0), 0)

    def test_pile_stays_when_nothing_accepts_it(self):
        closed = self.m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        closed.filter = set()
        self.m.items.add("sandstone", 20, 3, 7).sweep = dict(SWEEP)
        run(self.m, 20)
        self.assertEqual(closed.store.get("sandstone", 0), 0)
        self.assertAlmostEqual(self.m.items.totals().get("sandstone", 0), 20, places=1)


class ContainerTests(unittest.TestCase):
    def test_deliver_averages_temperature_by_mass(self):
        m = floor_world()
        b = m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        b.deliver("sandstone", 10, 40.0)
        b.deliver("sandstone", 10, 0.0)
        self.assertAlmostEqual(b.store_temp["sandstone"], 20.0)

    def test_germs_stay_on_the_structure_and_a_take_carries_a_share(self):
        m = floor_world()
        b = m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        b.deliver("sandstone", 10, 20.0, 8.0)
        self.assertAlmostEqual(b.germs, 8.0)
        kg, temp, g = b.take("sandstone", 5)
        self.assertAlmostEqual(kg, 5)
        self.assertGreater(g, 0)
        self.assertAlmostEqual(g + b.germs, 8.0)

    def test_debris_germs_and_temperature_reach_the_storage(self):
        m = floor_world()
        dupes.spawn(m, 1, 6, 7)
        b = m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        m.items.add("sandstone", 10, 3, 7, 60.0, 5.0).sweep = dict(SWEEP)
        self.assertTrue(run(m, 60, until=lambda: b.store.get("sandstone", 0) > 9))
        self.assertGreater(b.germs, 0)
        self.assertGreater(b.store_temp["sandstone"], 40)


class GermTests(unittest.TestCase):
    def test_touch_moves_germs_onto_a_clean_structure_and_conserves(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 6, 7)[0]
        b = m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        d.germs = 100.0
        germs.touch(m, d, b, 1.0)
        self.assertGreater(b.germs, 0)
        self.assertLess(d.germs, 100.0)
        self.assertAlmostEqual(d.germs + b.germs, 100.0)

    def test_structure_and_debris_germs_die_off(self):
        m = floor_world()
        b = m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        b.germs = 50.0
        it = m.items.add("sandstone", 5, 3, 7, 20.0, 50.0)
        germs.step(m.world, m.items, 10.0, m.buildings)
        self.assertLess(b.germs, 50.0)
        self.assertLess(it.germs, 50.0)


if __name__ == "__main__":
    unittest.main()

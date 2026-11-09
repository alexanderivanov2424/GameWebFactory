"""Deep Colony: regression tests from a logic review."""

import unittest
from importlib import import_module

match_mod = import_module("games.deep-colony.logic.match")
Match = match_mod.Match


class ReviewTests(unittest.TestCase):
    def test_add_heat_on_tiny_gas_is_bounded(self):
        m = Match.blank(5, 5, "vacuum")
        m.world.set_cell(12, "oxygen", 0.002, 20)
        m.world.add_heat(12, 18.0)
        self.assertLess(m.world.temp[12], 200)

    def test_settle_merge_does_not_leak_reservation(self):
        m = Match.blank(3, 6, "vacuum")
        w = m.world
        for x in range(3):
            w.set_cell(w.idx(x, 5), "granite", 100, 20)
        a = m.items.add("coal", 5.0, 1, 4)
        b = m.items.add("coal", 5.0, 1, 1)
        b.reserved = 5.0
        m.items.settle(w)
        self.assertEqual(len(list(m.items)), 1)
        self.assertEqual(list(m.items)[0].reserved, 0.0)


if __name__ == "__main__":
    unittest.main()

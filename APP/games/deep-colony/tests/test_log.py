"""Deep Colony: colony log events (one short test per kind).
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_log.py
"""

import importlib
import unittest

content = importlib.import_module("games.deep-colony.logic.content")
dupes = importlib.import_module("games.deep-colony.logic.dupes")
machines = importlib.import_module("games.deep-colony.logic.machines")
orders = importlib.import_module("games.deep-colony.logic.orders")
Match = importlib.import_module("games.deep-colony.logic.match").Match


def lines(m):
    return list(m.log_entries.values())


def colonist():
    m = Match.blank(10, 10, "oxygen")
    return m, dupes.spawn(m, 1, 5, 5)[0]


class LogTests(unittest.TestCase):
    def test_suffocation_logged_once(self):
        m = Match.blank(10, 10, "vacuum")
        d = dupes.spawn(m, 1, 5, 5)[0]
        d.breath = 0.5
        for _ in range(5):
            dupes.update_needs(m, d, 1.0)
        self.assertEqual(sum("suffocating" in t for t in lines(m)), 1)

    def test_hunger_logged_once_and_rearmed(self):
        m, d = colonist()
        d.kcal = 400
        dupes.update_needs(m, d, 1.0)
        dupes.update_needs(m, d, 1.0)
        d.kcal = 3000
        dupes.update_needs(m, d, 1.0)
        d.kcal = 400
        dupes.update_needs(m, d, 1.0)
        self.assertEqual(sum("very hungry" in t for t in lines(m)), 2)

    def test_sickness_logged(self):
        m, d = colonist()
        d.sick = 100
        dupes.update_needs(m, d, 1.0)
        self.assertIn(f"{d.name} got sick.", lines(m))

    def test_stress_break_logged(self):
        m, d = colonist()
        d.stress, d.kcal = 99.99, 0
        dupes.update_needs(m, d, 1.0)
        self.assertTrue(any("stress break" in t for t in lines(m)))

    def test_first_building_logged_only_once(self):
        m = Match.blank(30, 20, "oxygen")
        for x in range(30):
            m.world.set_cell(m.world.idx(x, 15), "sandstone", 1000, 20)
        a = m.buildings.place("algae_oxygenator", 2, 13, "p1")
        b = m.buildings.place("algae_oxygenator", 10, 13, "p1")
        orders.finish_build(m, a)
        orders.finish_build(m, b)
        first = [t for t in lines(m) if t.startswith("First ")]
        self.assertEqual(len(first), 1)
        self.assertIn("planned by Ann", first[0])

    def test_machine_out_of_input_logged_once_after_having_it(self):
        m = Match.blank(30, 20, "oxygen")
        b = m.buildings.place("coal_generator", 2, 10, "p1", built=True)
        machines.coal_generator(m, b, 1.0)
        self.assertEqual(lines(m), [])           # never had coal: no message
        b.store["coal"] = 1.0
        machines.coal_generator(m, b, 1.0)
        b.store["coal"] = 0.0
        machines.coal_generator(m, b, 1.0)
        machines.coal_generator(m, b, 1.0)
        self.assertEqual(sum("out of coal" in t for t in lines(m)), 1)


if __name__ == "__main__":
    unittest.main()

"""Deep Colony: navigation and colonist behaviour tests on small hand-made worlds.
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_colonists.py
"""

import unittest
from importlib import import_module
from unittest import mock

match_mod = import_module("games.deep-colony.logic.match")
chores = import_module("games.deep-colony.logic.chores")
dupes = import_module("games.deep-colony.logic.dupes")
machines = import_module("games.deep-colony.logic.machines")
nav = import_module("games.deep-colony.logic.nav")
orders = import_module("games.deep-colony.logic.orders")

W, H = 20, 10


def floor_world(fill="oxygen"):
    """A 20x10 world with solid rows y=8 and y=9; standing row is y=7."""
    m = match_mod.Match.blank(W, H, fill)
    for x in range(W):
        for y in (8, 9):
            m.world.set_cell(m.world.idx(x, y), "sandstone", 1000, 20)
    return m


def rock(m, x, y):
    m.world.set_cell(m.world.idx(x, y), "sandstone", 1000, 20)


def run(m, seconds, dt=0.1, until=None):
    for _ in range(int(seconds / dt)):
        m.step(dt)
        if until and until():
            return True
    return until() if until else None


class NavTests(unittest.TestCase):
    def test_standable(self):
        m = floor_world()
        w = m.world
        self.assertTrue(nav.standable(w, 5, 7))
        self.assertFalse(nav.standable(w, 5, 5))     # mid-air
        self.assertFalse(nav.standable(w, 5, 8))     # inside rock
        w.ladder[w.idx(5, 5)] = True
        self.assertTrue(nav.standable(w, 5, 5))      # a ladder holds you up
        self.assertTrue(nav.standable(w, 5, 4))      # the cell above a ladder top

    def test_walking_off_a_ledge_falls_to_the_floor(self):
        m = floor_world()
        w = m.world
        for x in range(10, W):
            w.set_cell(w.idx(x, 8), "oxygen", 1.0, 20)   # a pit two cells deep
        dist, _ = nav.distances(w, w.idx(5, 7))
        self.assertIn(w.idx(10, 8), dist)
        self.assertTrue(any(w.xy(i)[0] == 12 and w.xy(i)[1] == 8 for i in dist))
        p = nav.path(w, nav.distances(w, w.idx(9, 7))[1], w.idx(9, 7), w.idx(10, 8))
        self.assertEqual([w.xy(i) for i in p], [(10, 7), (10, 8)])   # sideways, then down

    def test_step_up_one_block(self):
        m = floor_world()
        w = m.world
        rock(m, 5, 7)
        dist, parent = nav.distances(w, w.idx(3, 7))
        self.assertIn(w.idx(5, 6), dist)
        p = nav.path(w, parent, w.idx(3, 7), w.idx(5, 6))
        self.assertEqual([w.xy(i) for i in p], [(4, 7), (4, 6), (5, 6)])
        rock(m, 5, 6)      # two blocks high: no way over
        dist, _ = nav.distances(w, w.idx(3, 7))
        self.assertNotIn(w.idx(6, 7), dist)

    def test_ladder_climb(self):
        m = floor_world()
        w = m.world
        for x in range(6, 10):
            rock(m, x, 4)
        for y in range(3, 8):
            w.ladder[w.idx(5, y)] = True
        dist, parent = nav.distances(w, w.idx(3, 7))
        self.assertIn(w.idx(7, 3), dist)
        p = nav.path(w, parent, w.idx(3, 7), w.idx(7, 3))
        self.assertIn((5, 5), [w.xy(i) for i in p])

    def test_colonist_walks_to_a_goal(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        w = m.world
        dist, parent = nav.distances(w, d.cell(w))
        d.path = nav.path(w, parent, d.cell(w), w.idx(9, 7))
        for _ in range(40):
            dupes.advance(m, d, 0.1)
        self.assertEqual((d.cx, d.cy), (9, 7))
        self.assertFalse(d.path)


class ColonistTests(unittest.TestCase):
    def test_digs_a_marked_cell(self):
        m = floor_world()
        rock(m, 8, 7)
        dupes.spawn(m, 1, 5, 7)
        orders.dig(m, "p1", [(8, 7)])
        i = m.world.idx(8, 7)
        self.assertTrue(run(m, 60, until=lambda: i not in m.digs))
        self.assertTrue(m.world.is_vacuum(i) or not m.world.is_solid(i))
        self.assertGreater(m.items.totals().get("sandstone", 0), 0)

    def test_site_is_supplied_from_debris_and_built(self):
        m = floor_world()
        dupes.spawn(m, 1, 3, 7)
        m.items.add("sandstone", 100, 12, 7)
        b = m.buildings.place("ladder", 6, 7, "p1")
        self.assertTrue(run(m, 120, until=lambda: b.built))
        self.assertTrue(m.world.ladder[m.world.idx(6, 7)])
        self.assertEqual(b.reserved, {})

    def test_debris_is_hauled_into_storage(self):
        m = floor_world()
        dupes.spawn(m, 1, 6, 7)
        bin_ = m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        item = m.items.add("sandstone", 50, 3, 7)
        self.assertTrue(run(m, 60, until=lambda: bin_.store.get("sandstone", 0) > 49))
        self.assertAlmostEqual(bin_.store.get("sandstone", 0), 50, places=1)
        self.assertEqual(item.reserved, 0)

    def test_vacuum_costs_breath_then_health(self):
        m = floor_world("vacuum")
        d = dupes.spawn(m, 1, 5, 7)[0]
        chores.step(m, 3.0)
        self.assertLess(d.breath, 100)
        self.assertEqual(d.health, 100)
        d.breath = 0
        chores.step(m, 2.0)
        self.assertLess(d.health, 100)
        chores.step(m, 20.0)
        self.assertTrue(d.dead)
        self.assertEqual(d.death, "suffocated")

    def test_breathing_uses_gas_and_exhales_carbon_dioxide(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 5, 7)[0]
        d.breath = 50
        before = m.world.mass[m.world.idx(5, 7)]
        dupes.update_needs(m, d, 1.0)
        self.assertGreater(d.breath, 50)
        self.assertLess(m.world.mass[m.world.idx(5, 7)], before)

    def test_eats_from_a_storage_building(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        bin_ = m.buildings.place("storage_bin", 8, 7, "p1", built=True)
        bin_.store["nutrient_bar"] = 2.0
        d.kcal = 1000
        self.assertTrue(run(m, 40, until=lambda: d.kcal > 1500))
        self.assertLess(bin_.store.get("nutrient_bar", 0), 2.0)
        self.assertEqual(bin_.reserved, {})

    def test_cancel_for_releases_reservations(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        item = m.items.add("sandstone", 100, 12, 7)
        b = m.buildings.place("ladder", 6, 7, "p1")
        chores.step(m, 0.1)
        self.assertTrue(b.reserved)
        self.assertGreater(item.reserved, 0)
        chores.cancel_for(m, ("building", b.id))
        self.assertEqual(b.reserved, {})
        self.assertEqual(item.reserved, 0)
        self.assertEqual(d.task, "Idle")

    def test_cancel_for_a_dig_releases_the_claim(self):
        m = floor_world()
        rock(m, 8, 7)
        dupes.spawn(m, 1, 5, 7)
        orders.dig(m, "p1", [(8, 7)])
        i = m.world.idx(8, 7)
        chores.step(m, 0.1)
        self.assertNotEqual(m.digs[i]["claimed"], "")
        chores.cancel_for(m, ("dig", i))
        self.assertEqual(m.digs[i]["claimed"], "")

    def test_a_dropped_load_becomes_debris(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 5, 7)[0]
        m.items.add("sandstone", 100, 5, 7)
        m.buildings.place("storage_bin", 10, 7, "p1", built=True)
        chores.step(m, 0.1)           # chose a haul chore and reserved the pile
        chores.step(m, 0.3)           # picked it up
        self.assertIsNotNone(d.carry)
        chores.cancel_for(m, ("building", m.buildings.at(10, 7).id))
        self.assertIsNone(d.carry)
        self.assertGreater(m.items.totals().get("sandstone", 0), 99)

    def test_without_a_toilet_the_colonist_pees_on_the_floor(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 5, 7)[0]
        d.bladder = 100
        stress = d.stress
        run(m, 6)
        self.assertLess(d.bladder, 50)
        self.assertGreater(d.stress, stress + 10)
        w = m.world
        self.assertTrue(any(w.element_id(i) == "polluted_water" for i in range(w.n)))

    def test_uses_a_usable_toilet(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        b = m.buildings.place("outhouse", 8, 6, "p1", built=True)
        d.bladder = 100

        def use(match, tb, dupe):
            dupe.bladder = 0

        with mock.patch.object(machines, "toilet_usable", lambda match, tb: True, create=True), \
                mock.patch.object(machines, "use_toilet", use, create=True):
            self.assertTrue(run(m, 40, until=lambda: d.bladder == 0))
        self.assertFalse(any(m.world.element_id(i) == "polluted_water" for i in range(m.world.n)))
        self.assertIn(b.id, m.buildings.by_id)

    def test_high_germs_make_a_colonist_sick(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 5, 7)[0]
        d.germs = 1e6
        for _ in range(40):
            dupes.update_needs(m, d, 1.0)
        self.assertGreater(d.sick, 0)

    def test_stress_break_pauses_work_then_resets_stress(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 5, 7)[0]
        d.stress, d.kcal = 99.99, 0      # hunger pushes it over the edge
        chores.step(m, 1.0)
        self.assertEqual(d.task, "Stress break")
        chores.step(m, 31)
        self.assertEqual(d.stress_break, 0)
        self.assertAlmostEqual(d.stress, 60, delta=1)


if __name__ == "__main__":
    unittest.main()

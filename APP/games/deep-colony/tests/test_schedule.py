"""Deep Colony: schedules, sleep/stamina and the Research Station through colonists.
Run: cd APP && python3 -B -m unittest discover -s games/deep-colony/tests -p test_schedule.py
"""

import unittest
from importlib import import_module

from gamekit import LobbyError

match_mod = import_module("games.deep-colony.logic.match")
content = import_module("games.deep-colony.logic.content")
dupes = import_module("games.deep-colony.logic.dupes")
orders = import_module("games.deep-colony.logic.orders")
research = import_module("games.deep-colony.logic.research")
schedule = import_module("games.deep-colony.logic.schedule")

W, H = 20, 10
HOUR = 600.0 / 24


def floor_world():
    m = match_mod.Match.blank(W, H, "oxygen")
    for x in range(W):
        for y in (8, 9):
            m.world.set_cell(m.world.idx(x, y), "sandstone", 1000, 20)
    return m


def at_hour(m, hour):
    m.time = hour * HOUR + 1.0


def run(m, seconds, dt=0.1, until=None):
    for _ in range(int(seconds / dt)):
        m.step(dt)
        if until and until():
            return True
    return until() if until else None


def blocks(m, hour, block):
    return "w" * 24 if block == "w" else "".join(block if h == hour else "w" for h in range(24))


class ScheduleTests(unittest.TestCase):
    def test_block_for_follows_the_hour(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        m.schedules.set_blocks("p1", "1", "w" * 6 + "d" * 6 + "s" * 6 + "w" * 6)
        for hour, want in ((0, "w"), (7, "d"), (13, "s"), (20, "w")):
            at_hour(m, hour)
            self.assertEqual(m.schedules.block_for(d), want)

    def test_set_blocks_rejects_bad_strings(self):
        m = floor_world()
        for bad in ("w" * 23, "w" * 25, "x" * 24, None, "W" * 24):
            with self.assertRaises(LobbyError):
                m.schedules.set_blocks("p1", "1", bad)
        with self.assertRaises(LobbyError):
            m.schedules.set_blocks("p1", "9", "w" * 24)

    def test_assign_moves_a_colonist(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        m.schedules.set_blocks("p1", "2", "s" * 24)
        m.schedules.assign("p1", d.id, "2")
        self.assertEqual(d.schedule, "2")
        self.assertEqual(m.schedules.block_for(d), "s")
        with self.assertRaises(LobbyError):
            m.schedules.assign("p1", "nobody", "2")
        with self.assertRaises(LobbyError):
            m.schedules.assign("p1", d.id, "7")


class SleepTests(unittest.TestCase):
    def sleepy(self, cot):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        d.bladder, d.stamina = 0.0, 50.0
        m.schedules.set_blocks("p1", "1", "s" * 24)
        b = m.buildings.place("cot", 10, 7, "p1", built=True) if cot else None
        return m, d, b

    def test_walks_to_a_free_cot_and_sleeps(self):
        m, d, b = self.sleepy(True)
        self.assertTrue(run(m, 20, until=lambda: d.asleep))
        self.assertIn(m.world.idx(d.cx, d.cy), {m.world.idx(x, y) for x, y in b.cells()})
        s0 = d.stamina
        run(m, 10)
        self.assertGreater(d.stamina, s0)
        self.assertEqual(d.task, "Sleeping")

    def test_one_cot_per_colonist(self):
        m, d, b = self.sleepy(True)
        d2 = dupes.spawn(m, 1, 4, 7)[0]
        d2.bladder, d2.stamina = 0.0, 50.0
        run(m, 20)
        self.assertTrue(d.asleep and d2.asleep)
        on_cot = [e for e in (d, d2) if (e.cx, e.cy) in set(b.cells())]
        self.assertEqual(len(on_cot), 1)

    def test_floor_sleep_is_slower_and_stressful(self):
        m, d, _ = self.sleepy(False)
        d.stress = 10.0
        run(m, 5)
        self.assertTrue(d.asleep)
        self.assertEqual((d.cx, d.cy), (3, 7))
        s0, st0 = d.stamina, d.stress
        run(m, 10)
        gain_floor = d.stamina - s0
        self.assertGreater(gain_floor, 0)
        self.assertGreater(d.stress, st0)
        m2, d2, _ = self.sleepy(True)
        run(m2, 20, until=lambda: d2.asleep)
        s1 = d2.stamina
        run(m2, 10)
        self.assertGreater(d2.stamina - s1, gain_floor)

    def test_wakes_when_block_ends(self):
        m, d, _ = self.sleepy(False)
        run(m, 3)
        self.assertTrue(d.asleep)
        m.schedules.set_blocks("p1", "1", "w" * 24)
        run(m, 2)
        self.assertFalse(d.asleep)

    def test_zero_stamina_sleeps_on_the_spot(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        d.bladder, d.stamina = 0.0, 0.0
        at_hour(m, 5)
        self.assertEqual(m.schedules.block_for(d), "w")
        run(m, 1)
        self.assertTrue(d.asleep)
        self.assertEqual((d.cx, d.cy), (3, 7))
        run(m, 100, until=lambda: not d.asleep)
        self.assertFalse(d.asleep)
        self.assertGreaterEqual(d.stamina, 30)

    def test_stamina_falls_while_awake(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        d.bladder = 0.0
        run(m, 10)
        self.assertLess(d.stamina, 100.0)


class DowntimeTests(unittest.TestCase):
    def test_downtime_skips_jobs_but_eats(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 5, 7)[0]
        d.bladder = 0.0
        m.world.set_cell(m.world.idx(8, 7), "sandstone", 1000, 20)
        orders.dig(m, "p1", [(8, 7)])
        m.schedules.set_blocks("p1", "1", "d" * 24)
        run(m, 10)
        self.assertIn(m.world.idx(8, 7), m.digs)
        food = next(e for e, v in content.ELEMENTS.items() if v.get("phase") == "food")
        m.items.add(food, 5.0, 6, 7, 20.0, 0.0)
        d.kcal = 1000.0
        self.assertTrue(run(m, 20, until=lambda: d.kcal > 1500))
        self.assertIn(m.world.idx(8, 7), m.digs)
        m.schedules.set_blocks("p1", "1", "w" * 24)
        self.assertTrue(run(m, 60, until=lambda: m.world.idx(8, 7) not in m.digs))


class ResearchTests(unittest.TestCase):
    def test_select_refuses_missing_prerequisites(self):
        m = floor_world()
        locked = next(t for t in research.TECHS.values() if t["requires"])
        with self.assertRaises(LobbyError):
            m.research.select("p1", locked["id"])
        with self.assertRaises(LobbyError):
            m.research.select("p1", "nope")

    def test_points_finish_a_tech_and_unlock_its_building(self):
        m = floor_world()
        tech = next(t for t in research.TECHS.values() if not t["requires"] and t["unlocks"])
        btype = tech["unlocks"][0]
        self.assertFalse(m.research.is_unlocked(btype))
        m.research.select("p1", tech["id"])
        m.research.add_points(tech["cost"])
        self.assertTrue(m.research.is_unlocked(btype))
        self.assertEqual(m.research.current, "")

    def test_colonist_operates_a_powered_station(self):
        m = floor_world()
        d = dupes.spawn(m, 1, 3, 7)[0]
        d.bladder = 0.0
        b = m.buildings.place("research_station", 8, 6, "p1", built=True)
        p = content.BUILDINGS["research_station"]["params"]
        b.deliver("dirt", p["dirtPerPoint"] * 5, 20.0)
        tech = next(t for t in research.TECHS.values() if not t["requires"])
        m.research.select("p1", tech["id"])
        m.networks.step = lambda dt: setattr(b, "powered", True)
        run(m, p["workPerPoint"] * 2 + 20)
        self.assertGreater(m.research.progress.get(tech["id"], 0) + (tech["cost"] if tech["id"] in m.research.done else 0), 0)
        self.assertLess(b.stored("dirt"), p["dirtPerPoint"] * 5)


if __name__ == "__main__":
    unittest.main()

"""Hex Realms: rules tests on logic.Match (one rule per test). Run: python3 -I tools/run_tests.py hex-realms"""

import importlib
import unittest

h = importlib.import_module("games.hex-realms.tests.helpers")
blank, hall, rich, stock, unit, well_fed = h.blank, h.hall, h.rich, h.stock, h.unit, h.well_fed
economy = importlib.import_module("games.hex-realms.logic.economy")
movement = importlib.import_module("games.hex-realms.logic.movement")


def end_turn(m):
    for pid in m.alive():
        m.set_done(pid, True)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.m = blank()
        hall(self.m, "p1", "-6,0"), hall(self.m, "p2", "6,0")

    def test_build_pays_and_appears_after_the_turn(self):
        wood = stock(self.m, "p1")["wood"]
        self.m.act("p1", "build", "hut", "-7,0", 0)
        self.assertEqual(stock(self.m, "p1")["wood"], wood - 2)
        self.assertNotIn("-7,0", self.m.cell_structure)
        end_turn(self.m)
        self.assertEqual(self.m.structures[self.m.cell_structure["-7,0"]]["type"], "hut")

    def test_cancel_refunds(self):
        wood = stock(self.m, "p1")["wood"]
        self.m.act("p1", "build", "farm", "-8,1", 0)
        self.m.act("p1", "cancel", self.m.orders["p1"]["builds"][0]["id"])
        self.assertEqual(stock(self.m, "p1")["wood"], wood)

    def test_same_cell_by_two_players_fails_for_both(self):
        m = blank()
        hall(m, "p1", "-2,0"), hall(m, "p2", "1,0")
        for pid in ("p1", "p2"):
            m.territory["0,0"] = pid
            rich(m, pid, 20)
            m.act(pid, "build", "hut", "0,0", 0)
        m.territory = dict(m.territory)
        end_turn(m)
        self.assertNotIn("0,0", m.cell_structure)
        self.assertEqual([e["why"] for e in m.events if e["t"] == "failed"], ["Another player built there too."] * 2)


class EconomyTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(players=1)
        self.hall = hall(self.m, "p1", "0,0")  # cells 0,0 1,0 0,1

    def report(self):
        return economy.report(self.m, "p1")

    def put(self, stype, at, rot=0):
        return self.m.add_structure("p1", stype, at, rot)

    def test_jobs_need_people(self):
        farm = self.put("farm", "2,0")["id"]
        self.m.players["p1"]["pop"] = 0
        self.assertNotIn(farm, self.report()["staffed"])

    def test_starving_kills_everyone_who_cant_eat(self):
        p = self.m.players["p1"]
        p["pop"] = 10
        food = self.report()["income"]["food"]
        end_turn(self.m)
        self.assertEqual(p["pop"], food // economy.FOOD_PER_PERSON)

    def test_surplus_food_becomes_people_up_to_housing(self):
        p = self.m.players["p1"]
        p["pop"], food = 0, self.report()["income"]["food"]
        end_turn(self.m)
        self.assertEqual(p["pop"], food // economy.FOOD_PER_PERSON)  # as many as the surplus feeds
        well_fed(self)
        end_turn(self.m)
        self.assertEqual(p["pop"], self.report()["housing"])  # no further than the housing

    def test_stores_are_capped(self):
        self.m.structures[self.hall]["stock"]["wood"] = 25
        end_turn(self.m)
        self.assertEqual(stock(self.m, "p1")["wood"], 25)


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(face=1)  # dice never hit unless a test says so
        well_fed(self)  # units never starve in these tests
        hall(self.m, "p1", "-8,0"), hall(self.m, "p2", "8,0")

    def test_moves_happen_together(self):
        a = unit(self.m, "p1", "militia", "0,0")
        b = unit(self.m, "p1", "militia", "1,0")
        self.m.act("p1", "move", a, "1,0")
        self.m.act("p1", "move", b, "2,0")
        end_turn(self.m)
        self.assertEqual((self.m.units[a]["at"], self.m.units[b]["at"]), ("1,0", "2,0"))

    def test_passing_through_each_other_fights(self):
        a = unit(self.m, "p1", "militia", "0,0")
        b = unit(self.m, "p2", "militia", "1,0")
        self.m.act("p1", "move", a, "1,0")
        self.m.act("p2", "move", b, "0,0")
        end_turn(self.m)
        battle = next(e for e in self.m.events if e["t"] == "battle")
        self.assertEqual([len(d) for d in battle["rounds"][0]], [1, 1])  # both attack (militia: attack 1)
        self.assertEqual((self.m.units[a]["at"], self.m.units[b]["at"]), ("0,0", "1,0"))

    def test_same_target_fight_and_nobody_enters(self):
        a = unit(self.m, "p1", "militia", "0,0")
        b = unit(self.m, "p2", "militia", "2,0")
        self.m.act("p1", "move", a, "1,0")
        self.m.act("p2", "move", b, "1,0")
        end_turn(self.m)
        self.assertEqual(sum(1 for e in self.m.events if e["t"] == "battle"), 1)
        self.assertNotIn("1,0", self.m.unit_at)

    def test_attacking_a_standing_unit(self):
        self.m.rng.face = 6
        a = unit(self.m, "p1", "swordsman", "0,0")
        b = unit(self.m, "p2", "militia", "1,0")
        self.m.act("p1", "move", a, "1,0")
        end_turn(self.m)
        battle = next(e for e in self.m.events if e["t"] == "battle")
        self.assertEqual(len(battle["rounds"][0][0]), 4)  # attacker rolls attack dice
        self.assertEqual(len(battle["rounds"][0][1]), 2)  # defender rolls defense dice
        self.assertNotIn(b, self.m.units)
        self.assertEqual(self.m.units[a]["at"], "0,0")  # fighting stops the move

    def test_cover_needs_five(self):
        self.m.rng.face = 4
        a = unit(self.m, "p1", "swordsman", "0,0")
        b = unit(self.m, "p2", "militia", "1,0")
        self.m.cells["1,0"] = "forest"
        self.m.act("p1", "move", a, "1,0")
        end_turn(self.m)
        self.assertIn(b, self.m.units)

    def test_no_moving_through_enemy_walls(self):
        a = unit(self.m, "p1", "militia", "0,0")
        self.m.add_structure("p2", "wall", "1,0", 0)
        self.m.add_structure("p2", "wall", "1,-1", 0)
        self.m.add_structure("p2", "wall", "0,1", 0)
        self.assertNotIn("2,0", movement.reach(self.m, a))
        self.m.act("p1", "move", a, "1,0")  # attacking it is fine

    def test_moving_over_enemy_structures(self):
        a = unit(self.m, "p1", "militia", "0,0")
        for at in ("1,0", "1,-1", "0,1"):
            self.m.add_structure("p2", "hut", at, 0)
        self.assertIn("2,0", movement.reach(self.m, a))


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(face=6)
        well_fed(self)  # units never starve in these tests
        self.h1, self.h2 = hall(self.m, "p1", "-8,0"), hall(self.m, "p2", "0,0")

    def test_archer_shoots_without_reply(self):
        self.m.players["p1"]["advances"].append("archery")
        a = unit(self.m, "p1", "archer", "-3,0")
        b = unit(self.m, "p2", "militia", "-1,0")
        self.m.act("p1", "shoot", a, "-1,0")
        end_turn(self.m)
        self.assertNotIn(b, self.m.units)
        self.assertEqual(self.m.units[a]["hp"], 2)

    def test_siege_damages_and_strikes_back(self):
        a = unit(self.m, "p1", "swordsman", "-2,0")
        self.m.act("p1", "move", a, "0,0")
        end_turn(self.m)
        siege = next(e for e in self.m.events if e["t"] == "siege")
        self.assertEqual(siege["damage"], 4)
        self.assertEqual(self.m.structures[self.h2]["hp"], 11)
        self.assertEqual(self.m.units[a]["hp"], 2)  # the hall's 2 dice hit back; no healing after a fight

    def test_losing_the_last_hall_knocks_you_out(self):
        self.m.structures[self.h2]["hp"] = 1
        a = unit(self.m, "p1", "militia", "-2,0")
        unit(self.m, "p2", "militia", "3,0")
        self.m.act("p1", "move", a, "0,0")
        end_turn(self.m)
        self.assertFalse(self.m.players["p2"]["alive"])
        self.assertFalse(any(u["owner"] == "p2" for u in self.m.units.values()))
        self.assertEqual(self.m.result["winner"], "p1")


class CityTests(unittest.TestCase):
    def setUp(self):
        well_fed(self)  # units never starve in these tests
        self.m = blank()
        hall(self.m, "p1", "-8,0"), hall(self.m, "p2", "8,0")

    def test_settlers_found_a_city(self):
        s = unit(self.m, "p1", "settlers", "0,0")
        self.m.act("p1", "found", s, 0)
        end_turn(self.m)
        self.assertEqual(self.m.structures[self.m.cell_structure["0,0"]]["type"], "town_hall")
        self.assertNotIn(s, self.m.units)


class FogTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(fog="on", face=1)
        well_fed(self)  # units never starve in these tests
        hall(self.m, "p1", "-8,8"), hall(self.m, "p2", "8,-8")  # far away: they keep both players in

    def view(self, pid="p1"):
        return self.m.private(pid)["view"]

    def test_units_see_two_cells(self):
        unit(self.m, "p1", "militia", "0,0")
        near = unit(self.m, "p2", "militia", "2,0")
        far = unit(self.m, "p2", "militia", "3,0")
        self.m.refresh()
        units = self.view()["units"]
        self.assertIn(near, units)
        self.assertNotIn(far, units)
        self.assertNotIn("4,0", self.view()["cells"])  # unexplored: no terrain either

    def test_enemy_structures_are_remembered_until_seen_gone(self):
        u = unit(self.m, "p1", "militia", "0,0")
        hut = self.m.add_structure("p2", "hut", "2,0", 0)["id"]
        self.m.refresh()
        self.m.move_unit(u, "-6,0")
        self.m.refresh()
        self.assertIn(hut, self.view()["structures"])  # out of sight: as last seen
        self.m.remove_structure(hut)
        self.m.refresh()
        self.assertIn(hut, self.view()["structures"])  # still don't know it's gone
        self.m.move_unit(u, "0,0")
        self.m.refresh()
        self.assertNotIn(hut, self.view()["structures"])

    def test_spectators_see_everything(self):
        far = unit(self.m, "p2", "militia", "8,0")
        self.m.refresh()
        self.assertIn(far, self.m.private(None)["view"]["units"])

    def test_hidden_enemies_dont_block_planning(self):
        u = unit(self.m, "p1", "militia", "0,0")
        hidden = unit(self.m, "p2", "militia", "1,0")
        self.m.refresh()
        self.m.visible["p1"].discard("1,0")
        self.m.act("p1", "move", u, "2,0")  # through the unseen enemy
        end_turn(self.m)
        self.assertTrue(any(e["t"] == "battle" for e in self.m.events))
        self.assertIn(hidden, self.m.units)


class EndTests(unittest.TestCase):
    def test_turn_limit_highest_score_wins(self):
        m = blank(turns=10)
        hall(m, "p1", "-8,0"), hall(m, "p2", "8,0")
        m.players["p2"]["advances"].append("masonry")
        m.turn = 10
        end_turn(m)
        self.assertEqual(m.result["winner"], "p2")

    def test_leaving_player_hands_the_win(self):
        m = blank(players=3)
        hall(m, "p1", "-8,0"), hall(m, "p2", "8,0"), hall(m, "p3", "0,8")
        m.remove("p1")
        self.assertIsNone(m.result)
        m.remove("p2")
        self.assertEqual(m.result["winner"], "p3")


if __name__ == "__main__":
    unittest.main()

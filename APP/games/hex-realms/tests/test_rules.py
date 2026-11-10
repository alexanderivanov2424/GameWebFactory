"""Hex Realms: rules tests on logic.Match (one rule per test). Run: python3 -I tools/run_tests.py hex-realms"""

import importlib
import random
import unittest

from gamekit import LobbyError

h = importlib.import_module("games.hex-realms.tests.helpers")
Match, blank, hall, rich, unit = h.Match, h.blank, h.hall, h.rich, h.unit


def end_turn(m):
    for pid in m.alive():
        m.set_done(pid, True)


class StartTests(unittest.TestCase):
    def test_everyone_starts_with_a_hall_and_a_militia(self):
        m = Match({"p1": "A", "p2": "B", "p3": "C"}, {"turns": 40, "mapSize": "normal", "seed": 7}, rng=random.Random(3))
        for pid in m.seats:
            self.assertEqual([s["type"] for s in m.structures.values() if s["owner"] == pid], ["town_hall"])
            self.assertEqual([u["type"] for u in m.units.values() if u["owner"] == pid], ["militia"])

    def test_turn_resolves_when_everyone_is_done(self):
        m = blank()
        hall(m, "p1", "-6,0"), hall(m, "p2", "6,0")
        m.set_done("p1", True)
        self.assertEqual(m.turn, 1)
        m.set_done("p2", True)
        self.assertEqual(m.turn, 2)

    def test_an_order_takes_back_end_turn(self):
        m = blank()
        hall(m, "p1", "-6,0"), hall(m, "p2", "6,0")
        m.set_done("p1", True)
        m.act("p1", "build", "road", "-7,0", 0)
        self.assertFalse(m.players["p1"]["done"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.m = blank()
        hall(self.m, "p1", "-6,0"), hall(self.m, "p2", "6,0")

    def test_build_pays_and_appears_after_the_turn(self):
        wood = self.m.players["p1"]["res"]["wood"]
        self.m.act("p1", "build", "road", "-7,0", 0)
        self.assertEqual(self.m.players["p1"]["res"]["wood"], wood - 1)
        self.assertNotIn("-7,0", self.m.cell_structure)
        end_turn(self.m)
        self.assertEqual(self.m.structures[self.m.cell_structure["-7,0"]]["type"], "road")

    def test_outside_territory_is_refused(self):
        with self.assertRaisesRegex(LobbyError, "territory"):
            self.m.act("p1", "build", "hut", "0,0", 0)

    def test_must_touch_own_structure(self):
        with self.assertRaisesRegex(LobbyError, "touch"):
            self.m.act("p1", "build", "hut", "-8,0", 0)

    def test_chain_of_pending_builds(self):
        self.m.act("p1", "build", "road", "-7,0", 0)
        self.m.act("p1", "build", "road", "-8,0", 0)

    def test_advance_required(self):
        rich(self.m, "p1")
        with self.assertRaisesRegex(LobbyError, "Masonry"):
            self.m.act("p1", "build", "wall", "-7,0", 0)

    def test_terrain_rule(self):
        with self.assertRaisesRegex(LobbyError, "grassland"):
            self.m.act("p1", "build", "mine", "-7,0", 0)

    def test_cancel_refunds(self):
        wood = self.m.players["p1"]["res"]["wood"]
        self.m.act("p1", "build", "farm", "-8,1", 0)
        self.m.act("p1", "cancel", self.m.orders["p1"]["builds"][0]["id"])
        self.assertEqual(self.m.players["p1"]["res"]["wood"], wood)

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
        self.hall = hall(self.m, "p1", "0,0")

    def report(self):
        from importlib import import_module
        return import_module("games.hex-realms.logic.economy").report(self.m, "p1")

    def test_unconnected_structure_does_not_work(self):
        farm = self.m.add_structure("p1", "farm", "4,0", 0)["id"]
        self.assertNotIn(farm, self.report()["staffed"])
        for at in ("2,0", "3,0"):
            self.m.add_structure("p1", "road", at, 0)
        self.assertIn(farm, self.report()["staffed"])

    def test_jobs_need_people(self):
        farm = self.m.add_structure("p1", "farm", "2,0", 0)["id"]
        self.m.players["p1"]["pop"] = 0
        self.assertNotIn(farm, self.report()["staffed"])

    def test_switched_off_frees_workers(self):
        farm = self.m.add_structure("p1", "farm", "2,0", 0)["id"]
        self.m.act("p1", "toggle", farm)
        rep = self.report()
        self.assertNotIn(farm, rep["staffed"])
        self.assertEqual(rep["idle"], self.m.players["p1"]["pop"])

    def test_farm_gets_grass_bonus(self):
        self.m.add_structure("p1", "farm", "2,0", 0)
        with_grass = self.report()["income"]["food"]
        for c in ("2,0", "3,0", "2,1"):
            self.m.cells[c] = "plains"
        self.assertEqual(self.report()["income"]["food"], with_grass - 3)

    def test_starving_loses_a_person(self):
        p = self.m.players["p1"]
        p["res"]["food"], p["pop"] = 0, 10
        end_turn(self.m)
        self.assertEqual(p["pop"], 9)

    def test_growth_needs_housing(self):
        p = self.m.players["p1"]
        p["pop"] = self.report()["housing"]
        end_turn(self.m)
        self.assertEqual(p["pop"], self.report()["housing"])
        p["pop"] -= 1
        end_turn(self.m)
        self.assertEqual(p["pop"], self.report()["housing"])

    def test_storage_caps(self):
        self.m.players["p1"]["res"]["wood"] = 500
        end_turn(self.m)
        self.assertEqual(self.m.players["p1"]["res"]["wood"], self.report()["caps"]["wood"])

    def test_market_trade(self):
        with self.assertRaisesRegex(LobbyError, "Market"):
            self.m.act("p1", "trade", "wood", "stone")
        self.m.add_structure("p1", "market", "2,0", 0)
        wood, stone = self.m.players["p1"]["res"]["wood"], self.m.players["p1"]["res"]["stone"]
        self.m.act("p1", "trade", "wood", "stone")
        self.assertEqual((self.m.players["p1"]["res"]["wood"], self.m.players["p1"]["res"]["stone"]), (wood - 3, stone + 1))


class MovementTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(face=1)  # dice never hit unless a test says so
        hall(self.m, "p1", "-8,0"), hall(self.m, "p2", "8,0")

    def test_path_cost_and_roads(self):
        u = unit(self.m, "p1", "militia", "0,0")
        with self.assertRaisesRegex(LobbyError, "can't get there"):
            self.m.act("p1", "move", u, "3,0")
        for at in ("1,0", "2,0", "3,0"):
            self.m.add_structure("p1", "road", at, 0)
        self.m.act("p1", "move", u, "3,0")

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

    def test_friend_in_the_way_stops(self):
        a = unit(self.m, "p1", "militia", "0,0")
        unit(self.m, "p1", "militia", "1,0")
        self.m.act("p1", "move", a, "2,0")
        end_turn(self.m)
        self.assertEqual(self.m.units[a]["at"], "0,0")

    def test_no_moving_through_enemy_structures(self):
        a = unit(self.m, "p1", "militia", "0,0")
        self.m.add_structure("p2", "hut", "1,0", 0)
        self.m.add_structure("p2", "hut", "1,-1", 0)
        self.m.add_structure("p2", "hut", "0,1", 0)
        with self.assertRaisesRegex(LobbyError, "can't get there"):
            self.m.act("p1", "move", a, "2,0")
        self.m.act("p1", "move", a, "1,0")  # attacking it is fine

    def test_hold_adds_a_defense_die(self):
        a = unit(self.m, "p1", "militia", "0,0")
        b = unit(self.m, "p2", "militia", "1,0")
        self.m.act("p1", "hold", a)
        self.m.act("p2", "move", b, "0,0")
        end_turn(self.m)
        battle = next(e for e in self.m.events if e["t"] == "battle")
        self.assertEqual(len(battle["rounds"][0][1]), 3)


class CombatTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(face=6)
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

    def test_tower_shoots_nearest_enemy(self):
        t = self.m.add_structure("p1", "tower", "-6,0", 0)["id"]
        b = unit(self.m, "p2", "militia", "-4,0")
        end_turn(self.m)
        self.assertEqual(next(e for e in self.m.events if e["t"] == "tower")["structure"], t)
        self.assertNotIn(b, self.m.units)


class CityTests(unittest.TestCase):
    def setUp(self):
        self.m = blank()
        hall(self.m, "p1", "-8,0"), hall(self.m, "p2", "8,0")

    def test_settlers_found_a_city(self):
        s = unit(self.m, "p1", "settlers", "0,0")
        self.m.act("p1", "found", s, 0)
        end_turn(self.m)
        self.assertEqual(self.m.structures[self.m.cell_structure["0,0"]]["type"], "town_hall")
        self.assertNotIn(s, self.m.units)

    def test_too_close_to_a_hall(self):
        s = unit(self.m, "p1", "settlers", "-5,0")
        with self.assertRaisesRegex(LobbyError, "Too close"):
            self.m.act("p1", "found", s, 0)

    def test_recruit_uses_people_and_appears(self):
        sid = self.m.cell_structure["-8,0"]
        pop = self.m.players["p1"]["pop"]
        self.m.act("p1", "recruit", sid, "militia")
        self.assertEqual(self.m.players["p1"]["pop"], pop - 1)
        with self.assertRaisesRegex(LobbyError, "per structure"):
            self.m.act("p1", "recruit", sid, "militia")
        end_turn(self.m)
        self.assertEqual(sum(1 for u in self.m.units.values() if u["owner"] == "p1"), 1)


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

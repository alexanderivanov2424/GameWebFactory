"""Hex Realms: rules tests on logic.Match (one rule per test). Run: python3 -I tools/run_tests.py hex-realms"""

import importlib
import random
import unittest

from gamekit import LobbyError

h = importlib.import_module("games.hex-realms.tests.helpers")
Match, blank, hall, rich, stock, unit = h.Match, h.blank, h.hall, h.rich, h.stock, h.unit
economy = importlib.import_module("games.hex-realms.logic.economy")
movement = importlib.import_module("games.hex-realms.logic.movement")


def end_turn(m):
    for pid in m.alive():
        m.set_done(pid, True)


class StartTests(unittest.TestCase):
    def test_everyone_starts_with_settlers_only(self):
        m = Match({"p1": "A", "p2": "B", "p3": "C"}, {"turns": 40, "mapSize": "normal", "seed": 7}, rng=random.Random(3))
        self.assertEqual(m.structures, {})
        for pid in m.seats:
            self.assertEqual([u["type"] for u in m.units.values() if u["owner"] == pid], ["settlers"])

    def test_first_city_gets_the_starting_goods(self):
        m = Match({"p1": "A", "p2": "B"}, {"turns": 40, "mapSize": "normal", "seed": 7}, rng=random.Random(3))
        s = next(u for u, x in m.units.items() if x["owner"] == "p1")
        m.act("p1", "found", s, m.private("p1")["found"][s][0])
        end_turn(m)
        self.assertTrue(m.players["p2"]["alive"])  # no city yet, but settlers: still in
        self.assertEqual(stock(m, "p1")["wood"], h.match_mod.START_GOODS["wood"])

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
        wood = stock(self.m, "p1")["wood"]
        self.m.act("p1", "build", "road", "-7,0", 0)
        self.assertEqual(stock(self.m, "p1")["wood"], wood - 1)
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

    def test_structures_work_without_roads(self):
        farm = self.put("farm", "4,0")["id"]
        self.assertIn(farm, self.report()["staffed"])

    def test_jobs_need_people(self):
        farm = self.put("farm", "2,0")["id"]
        self.m.players["p1"]["pop"] = 0
        self.assertNotIn(farm, self.report()["staffed"])

    def test_switched_off_frees_workers(self):
        farm = self.put("farm", "2,0")["id"]
        self.m.act("p1", "toggle", farm)
        rep = self.report()
        self.assertNotIn(farm, rep["staffed"])
        self.assertEqual(rep["idle"], self.m.players["p1"]["pop"])

    def test_farm_gets_grass_bonus(self):
        self.put("farm", "2,0")
        with_grass = self.report()["income"]["food"]
        for c in ("2,0", "3,0", "2,1"):
            self.m.cells[c] = "plains"
        self.assertEqual(self.report()["income"]["food"], with_grass - 3)

    def test_starving_loses_a_person(self):
        p = self.m.players["p1"]
        self.m.structures[self.hall]["stock"]["food"], p["pop"] = 0, 10
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

    def test_stores_are_capped(self):
        self.m.structures[self.hall]["stock"]["wood"] = 25
        end_turn(self.m)
        self.assertEqual(stock(self.m, "p1")["wood"], 25)

    def test_market_trade(self):
        with self.assertRaisesRegex(LobbyError, "Market"):
            self.m.act("p1", "trade", "wood", "stone")
        self.put("market", "2,0")
        before = stock(self.m, "p1")
        self.m.act("p1", "trade", "wood", "stone")
        after = stock(self.m, "p1")
        self.assertEqual((after["wood"], after["stone"]), (before["wood"] - 3, before["stone"] + 1))


class LogisticsTests(unittest.TestCase):
    """Goods travel along road networks (roads + navigable structures) to stores."""

    def setUp(self):
        self.m = blank(players=1)
        self.hall = hall(self.m, "p1", "0,0")  # cells 0,0 1,0 0,1

    def put(self, stype, at, rot=0):
        return self.m.add_structure("p1", stype, at, rot)

    def roads(self, *cells):
        for c in cells:
            self.put("road", c)

    def test_without_a_road_goods_wait_in_the_producer(self):
        farm = self.put("farm", "2,0")  # touches the hall, but touching isn't a road
        made = economy.output(self.m, farm)["food"]
        end_turn(self.m)
        end_turn(self.m)
        self.assertEqual(farm["held"], {"food": made})  # one turn's output at most
        self.assertIn(farm["id"], economy.report(self.m, "p1")["stranded"])
        self.roads("2,-1")  # touches the hall's 1,0 and the farm's 2,0
        before = stock(self.m, "p1")["food"]
        end_turn(self.m)
        self.assertEqual(farm["held"], {})
        self.assertGreater(stock(self.m, "p1")["food"], before)

    def test_navigable_structures_extend_roads(self):
        self.put("storage_yard", "3,0")  # navigable: 3,0 4,0 3,1
        self.put("market", "5,0")  # navigable: 5,0 6,0 7,0
        farm = self.put("farm", "8,0")  # B - A - A
        self.assertIn(farm["id"], economy.report(self.m, "p1")["stranded"])  # no road in the chain yet
        self.roads("2,0")  # hall - road - A - A - B
        self.assertNotIn(farm["id"], economy.report(self.m, "p1")["stranded"])
        end_turn(self.m)
        self.assertEqual(farm["held"], {})

    def test_unlinked_store_fills_but_cannot_be_spent(self):
        mill = self.put("lumbermill", "6,0")  # 6,0 7,0
        self.roads("8,0")
        yard = self.put("storage_yard", "9,0")  # 9,0 10,0 9,1: on the road, not linked to the hall
        wood = stock(self.m, "p1")["wood"]
        end_turn(self.m)
        made = yard["stock"]["wood"]
        self.assertGreater(made, 0)
        self.assertEqual(mill["held"], {})
        self.assertEqual(economy.report(self.m, "p1")["unusable"]["wood"], made)
        self.assertEqual(stock(self.m, "p1")["wood"], wood)  # the hall makes no wood
        self.roads(*[f"{q},-1" for q in range(1, 10)])  # from the hall's 1,0 to the yard's 9,0
        self.assertEqual(stock(self.m, "p1")["wood"], wood + made)

    def test_spending_uses_linked_stores_too(self):
        self.m.structures[self.hall]["stock"]["wood"] = 0
        self.roads("2,0")
        yard = self.put("storage_yard", "3,0")
        yard["stock"]["wood"] = 5
        self.m.act("p1", "build", "hut", "-1,0", 0)
        self.assertEqual(yard["stock"]["wood"], 3)


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


class FogTests(unittest.TestCase):
    def setUp(self):
        self.m = blank(fog="on", face=1)
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

    def test_buildings_see_further(self):
        self.m.add_structure("p1", "hut", "0,0", 0)
        far = unit(self.m, "p2", "militia", "3,0")
        self.m.refresh()
        self.assertIn(far, self.view()["units"])

    def test_explored_cells_stay_but_dim(self):
        u = unit(self.m, "p1", "militia", "0,0")
        self.m.refresh()
        self.m.move_unit(u, "-6,0")
        self.m.refresh()
        view = self.view()
        self.assertIn("2,0", view["cells"])
        self.assertIn("2,0", view["dim"])

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

    def test_can_plan_into_unexplored_cells(self):
        u = unit(self.m, "p1", "militia", "0,0")
        self.m.refresh()
        self.m.act("p1", "move", u, "-2,0")  # within reach either way
        self.m.cells["3,0"] = "water"
        for k in ("1,0", "2,0"):
            self.m.explored["p1"].discard(k)
        self.assertIn("2,0", movement.reach(self.m, u))

    def test_unknown_rough_ground_stops_the_move(self):
        u = unit(self.m, "p1", "militia", "0,0")
        self.m.cells["2,0"] = "forest"
        self.m.refresh()
        self.m.explored["p1"] -= {"1,0", "2,0"}
        self.m.visible["p1"] -= {"1,0", "2,0"}
        self.m.act("p1", "move", u, "2,0")  # planned as open ground: 2 + 2
        end_turn(self.m)
        self.assertEqual(self.m.units[u]["at"], "1,0")  # the forest costs 4: not enough left

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

"""Bastion: Match rules tests (build turns, placement, orders, siege flow, market, leaving) with
fixture content (helpers.py).

Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

from gamekit import LobbyError

helpers = importlib.import_module("games.bastion.tests.helpers")
match_module = helpers.match_module
give, wave, level = helpers.give, helpers.wave, helpers.level


def setUpModule():
    helpers.install()


def tearDownModule():
    helpers.remove()


def end_all(match):
    for pid in list(match.seats):
        match.end_turn(pid) if match.stage == "build" else match.ready(pid)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.match = helpers.new_match()

    def play(self, card_id, x=None, y=None, pid="p1"):
        return self.match.play(pid, give(self.match, pid, card_id), x, y)

    def test_ground_structures_go_on_grass(self):
        self.play("t-tower", 3, 1)
        self.assertEqual(self.match.board.at(3, 1).owner, "p1")
        with self.assertRaisesRegex(LobbyError, "road"):
            self.play("t-tower", 3, 2)
        with self.assertRaisesRegex(LobbyError, "grass"):
            self.play("t-tower", 2, 0)  # rocks
        with self.assertRaisesRegex(LobbyError, "keep"):
            self.play("t-tower", 0, 2)

    def test_road_structures_go_on_the_road_but_not_the_entrance(self):
        self.play("t-wall", 3, 2)
        with self.assertRaisesRegex(LobbyError, "road"):
            self.play("t-wall", 3, 1)
        with self.assertRaisesRegex(LobbyError, "enters"):
            self.play("t-wall", 7, 2)

    def test_barracks_must_touch_the_road(self):
        with self.assertRaisesRegex(LobbyError, "next to the road"):
            self.play("t-barracks", 6, 0)
        self.play("t-barracks", 6, 1)

    def test_same_card_upgrades_for_extra_labor(self):
        seat = self.match.seats["p1"]
        seat.labor = 10
        self.play("t-tower", 3, 1)  # 2 labor
        self.play("t-tower", 3, 1)  # 2 + 1 per level
        self.assertEqual(seat.labor, 10 - 2 - 3)
        self.assertEqual(self.match.board.at(3, 1).level, 2)
        self.play("t-tower", 3, 1)  # 2 + 2
        self.assertEqual(seat.labor, 10 - 2 - 3 - 4)
        with self.assertRaisesRegex(LobbyError, "highest level"):
            self.play("t-tower", 3, 1)

    def test_other_card_on_a_structure_is_refused(self):
        self.play("t-tower", 3, 1)
        with self.assertRaisesRegex(LobbyError, "already built"):
            self.play("t-farm", 3, 1)

    def test_upgrade_repairs_walls(self):
        self.match.seats["p1"].labor = 10
        self.play("t-wall", 3, 2)
        self.match.board.at(3, 2).hp = 1
        self.play("t-wall", 3, 2)
        self.assertEqual(self.match.board.at(3, 2).hp, 20)

    def test_not_enough_labor(self):
        self.match.seats["p1"].labor = 1
        with self.assertRaisesRegex(LobbyError, "labor"):
            self.play("t-tower", 3, 1)
        self.assertIsNone(self.match.board.at(3, 1))

    def test_played_cards_are_discarded(self):
        seat = self.match.seats["p1"]
        uid = give(self.match, "p1", "t-tower")
        self.match.play("p1", uid, 3, 1)
        self.assertNotIn(uid, [c["uid"] for c in seat.hand])
        self.assertIn(uid, [c["uid"] for c in seat.deck.discard_pile])

    def test_card_not_in_hand(self):
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            self.match.play("p1", 999, 3, 1)

    def test_demolish_only_your_own(self):
        self.play("t-tower", 3, 1, pid="p2")
        with self.assertRaisesRegex(LobbyError, "your own"):
            self.match.demolish("p1", 3, 1)
        self.match.demolish("p2", 3, 1)
        self.assertIsNone(self.match.board.at(3, 1))

    def test_targets_list_legal_cells_with_their_labor(self):
        seat = self.match.seats["p1"]
        seat.hand = []
        seat.labor = 10
        give(self.match, "p1", "t-wall")
        targets = self.match.private("p1")["targets"]["t-wall"]
        self.assertIn("3,2", targets)
        self.assertNotIn("7,2", targets)  # entrance
        self.assertNotIn("3,1", targets)  # grass
        self.play("t-wall", 3, 2)
        give(self.match, "p1", "t-wall")
        self.assertEqual(self.match.private("p1")["targets"]["t-wall"]["3,2"], 2)  # upgrade: 1 + 1


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.match = helpers.new_match()

    def test_labor_and_draw(self):
        seat = self.match.seats["p1"]
        labor, hand = seat.labor, len(seat.hand)
        self.match.play("p1", give(self.match, "p1", "t-hustle"))
        self.assertEqual(seat.labor, labor + 2)
        self.assertEqual(len(seat.hand), hand + 1)

    def test_team_gold_goes_to_everyone_else(self):
        gold = {pid: s.gold for pid, s in self.match.seats.items()}
        self.match.play("p1", give(self.match, "p1", "t-gift"))
        self.assertEqual(self.match.seats["p1"].gold, gold["p1"])
        self.assertEqual(self.match.seats["p2"].gold, gold["p2"] + 2)

    def test_upgrade_order_needs_a_structure(self):
        with self.assertRaisesRegex(LobbyError, "structure"):
            self.match.play("p1", give(self.match, "p1", "t-mason"))
        helpers.build(self.match, "t-tower", 3, 1, owner="p2")
        self.match.play("p1", give(self.match, "p1", "t-mason"), 3, 1)
        self.assertEqual(self.match.board.at(3, 1).level, 2)

    def test_repair_and_keep_capped(self):
        wall = helpers.build(self.match, "t-wall", 3, 2)
        wall.hp = 3
        self.match.keep = 29
        self.match.play("p1", give(self.match, "p1", "t-fix"))
        self.assertEqual(wall.hp, 7)
        self.assertEqual(self.match.keep, 30)


class TurnTests(unittest.TestCase):
    def test_turn_advances_when_everyone_is_done(self):
        match = helpers.new_match(levels=[level(turns=2), level()])
        match.end_turn("p1")
        self.assertEqual(match.turn, 1)
        match.end_turn("p1", False)  # taken back
        match.end_turn("p2")
        self.assertEqual(match.turn, 1)
        match.end_turn("p1")
        self.assertEqual(match.turn, 2)
        self.assertFalse(any(s.done for s in match.seats.values()))

    def test_new_turn_refills_hand_labor_and_pays_farms(self):
        match = helpers.new_match(levels=[level(turns=2), level()])
        helpers.build(match, "t-farm", 5, 0, owner="p1", level=2)
        helpers.build(match, "t-quarry", 6, 0, owner="p2")
        gold = {pid: s.gold for pid, s in match.seats.items()}
        match.seats["p1"].labor = 0
        end_all(match)
        self.assertEqual(len(match.seats["p1"].hand), match_module.HAND_SIZE)
        self.assertEqual(match.seats["p1"].labor, match_module.LABOR)
        self.assertEqual(match.seats["p2"].labor, match_module.LABOR + 1)
        self.assertEqual(match.seats["p1"].gold, gold["p1"] + 2)
        self.assertEqual(match.seats["p2"].gold, gold["p2"])

    def test_done_players_cant_play(self):
        match = helpers.new_match()
        match.end_turn("p1")
        with self.assertRaisesRegex(LobbyError, "ended your turn"):
            match.play("p1", give(match, "p1", "t-hustle"))

    def test_last_build_turn_leads_to_siege_then_market(self):
        match = helpers.new_match(levels=[level(reward=7), level()])
        gold = match.seats["p1"].gold
        end_all(match)
        self.assertEqual(match.stage, "market")
        self.assertEqual(match.battle["level"], 1)
        self.assertEqual(match.keep, 30 - 2)  # one undefended grunt
        self.assertEqual(match.seats["p1"].gold, gold + 7)
        self.assertEqual(match.seats["p1"].hand, [])
        self.assertIn("market", match.public())
        self.assertIn("battle", match.public())

    def test_chapels_heal_after_a_siege(self):
        match = helpers.new_match(levels=[level(), level()])
        helpers.build(match, "t-chapel", 3, 1)
        wall = helpers.build(match, "t-wall", 2, 2, level=3)
        helpers.build(match, "t-tower", 4, 1)
        wall.hp = 10
        match.keep = 20
        end_all(match)
        self.assertEqual(match.keep, 22)
        self.assertGreaterEqual(wall.hp, 15)

    def test_keep_falling_loses(self):
        match = helpers.new_match(levels=[level(wave("t-grunt", 5)), level()], keepHealth=10)
        end_all(match)
        self.assertEqual(match.result["victory"], False)

    def test_holding_the_last_level_wins(self):
        match = helpers.new_match(levels=[level(), level()])
        helpers.build(match, "t-tower", 3, 1)
        end_all(match)  # siege 1
        end_all(match)  # market
        self.assertEqual(match.stage, "build")
        self.assertEqual(match.level, 1)
        end_all(match)  # siege 2
        self.assertEqual(match.result["victory"], True)

    def test_more_players_tougher_enemies(self):
        self.assertLess(helpers.new_match(players=1).hp_scale(), helpers.new_match(players=3).hp_scale())
        self.assertLess(helpers.new_match(difficulty="easy").hp_scale(), helpers.new_match(difficulty="hard").hp_scale())


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.match = helpers.new_match(levels=[level(), level(), level()])
        helpers.build(self.match, "t-tower", 3, 1)
        end_all(self.match)
        self.assertEqual(self.match.stage, "market")

    def test_build_actions_closed(self):
        with self.assertRaises(LobbyError):
            self.match.end_turn("p1")

    def test_buy_adds_a_card(self):
        seat = self.match.seats["p1"]
        seat.gold = 100
        before = len(seat.all_cards())
        card_id, cost = self.match.market.price(0)
        self.match.buy("p1", 0)
        self.assertEqual(seat.gold, 100 - cost)
        self.assertEqual(len(seat.all_cards()), before + 1)
        self.assertIn(card_id, seat.card_ids())
        self.match.buy("p2", 0) if self.match.seats["p2"].gold >= cost else None  # copies are unlimited
        self.assertEqual(self.match.market.offers[0], card_id)

    def test_cant_buy_without_gold(self):
        self.match.seats["p1"].gold = 0
        with self.assertRaisesRegex(LobbyError, "costs"):
            self.match.buy("p1", 0)
        with self.assertRaisesRegex(LobbyError, "empty"):
            self.match.buy("p1", 99)

    def test_retire_once_per_market(self):
        seat = self.match.seats["p1"]
        seat.gold = 10
        before = len(seat.all_cards())
        uid = seat.all_cards()[0]["uid"]
        self.match.retire("p1", uid)
        self.assertEqual(len(seat.all_cards()), before - 1)
        with self.assertRaisesRegex(LobbyError, "one card per market"):
            self.match.retire("p1", seat.all_cards()[0]["uid"])

    def test_retire_keeps_a_minimum_deck(self):
        seat = self.match.seats["p1"]
        seat.gold = 10
        seat.deck.draw_pile = seat.deck.draw_pile[:match_module.MIN_DECK]
        seat.deck.discard_pile = []
        with self.assertRaisesRegex(LobbyError, "below"):
            self.match.retire("p1", seat.all_cards()[0]["uid"])

    def test_everyone_ready_starts_the_next_level(self):
        self.match.ready("p1")
        self.assertEqual(self.match.stage, "market")
        self.match.ready("p2")
        self.assertEqual(self.match.stage, "build")
        self.assertEqual(self.match.level, 1)
        self.assertEqual(len(self.match.seats["p1"].hand), match_module.HAND_SIZE)


class LeaveTests(unittest.TestCase):
    def test_structures_pass_to_the_next_player(self):
        match = helpers.new_match(players=3)
        helpers.build(match, "t-farm", 5, 0, owner="p1")
        match.leave("p1")
        self.assertEqual(match.board.at(5, 0).owner, "p2")
        self.assertNotIn("p1", match.public()["seats"])

    def test_leaving_can_complete_the_turn(self):
        match = helpers.new_match(levels=[level(turns=2), level()])
        match.end_turn("p1")
        match.leave("p2")
        self.assertEqual(match.turn, 2)

    def test_everyone_leaving_ends_the_game(self):
        match = helpers.new_match(players=1)
        match.leave("p1")
        self.assertEqual(match.result["victory"], False)


if __name__ == "__main__":
    unittest.main()

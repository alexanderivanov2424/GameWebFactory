"""Bastion: playing cards on fixture content (blueprints, work, repair, cure, curses, gains), the
market and the done flag, through Match.
Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

from gamekit import LobbyError

helpers = importlib.import_module("games.bastion.tests.helpers")
give, build = helpers.give, helpers.build


def owned(match, pid="p1"):
    return [c["card"] for c in match.seats[pid].all_cards()]


def in_hand(match, uid, pid="p1"):
    return any(c["uid"] == uid for c in match.seats[pid].hand)


class BlueprintTests(helpers.FixtureCase):
    def test_build_pays_leaves_the_deck_and_adds_the_crew_card(self):
        match = helpers.new_match(self)
        match.stock["wood"] = 3
        uid = give(match, "p1", "plan-mill")
        match.play("p1", uid, 1, 1, 0)
        mill = match.board.structures[match.board.at[(1, 1)]]
        self.assertEqual((mill.kind, mill.owner, sorted(mill.cells)), ("mill", "p1", [(1, 1), (2, 1)]))
        self.assertEqual(match.stock["wood"], 2)
        self.assertNotIn("plan-mill", owned(match))
        self.assertIn("crew-mill", [c["card"] for c in match.seats["p1"].deck.discard_pile])

    def test_rotation_is_used(self):
        match = helpers.new_match(self)
        match.play("p1", give(match, "p1", "plan-ell"), 4, 2, 1)
        self.assertEqual(sorted(match.board.structures[match.board.at[(4, 2)]].cells),
                         sorted(match.board.footprint("ell", 1, 4, 2)))

    def test_a_building_can_give_another_card(self):
        match = helpers.new_match(self)
        match.play("p1", give(match, "p1", "plan-hut"), 5, 3)
        self.assertIn("work-any", [c["card"] for c in match.seats["p1"].deck.discard_pile])

    def test_reusable_blueprints_stay(self):
        match = helpers.new_match(self)
        uid = give(match, "p1", "plan-road")
        match.play("p1", uid, 4, 2, 0)
        self.assertEqual(match.board.roads, {(4, 2), (5, 2)})
        self.assertIn(uid, [c["uid"] for c in match.seats["p1"].deck.discard_pile])

    def test_refused_builds_change_nothing(self):
        match = helpers.new_match(self)
        match.stock["stone"] = 0
        wall = give(match, "p1", "plan-wall")
        with self.assertRaisesRegex(LobbyError, "short of stone"):
            match.play("p1", wall, 4, 2, 0)
        mill = give(match, "p1", "plan-mill")
        with self.assertRaisesRegex(LobbyError, "next to forest"):
            match.play("p1", mill, 4, 4, 0)
        with self.assertRaisesRegex(LobbyError, "Pick where"):
            match.play("p1", mill)
        self.assertTrue(in_hand(match, wall) and in_hand(match, mill))
        self.assertFalse(match.board.walls)
        self.assertEqual(list(match.board.structures), [1])  # just the keep


class WorkTests(helpers.FixtureCase):
    def test_work_card_works_its_kind_only(self):
        match = helpers.new_match(self)
        build(match, "shop", 4, 2)
        build(match, "mill", 1, 1)
        uid = give(match, "p1", "crew-mill")
        with self.assertRaisesRegex(LobbyError, "can't work a Shop"):
            match.play("p1", uid, 4, 2)
        match.play("p1", uid, 1, 1)
        self.assertEqual(match.board.structures[match.board.at[(1, 1)]].store, {"wood": 3})
        self.assertFalse(in_hand(match, uid))

    def test_needs_a_building(self):
        match = helpers.new_match(self)
        with self.assertRaisesRegex(LobbyError, "Pick a building"):
            match.play("p1", give(match, "p1", "work-any"), 5, 5)

    def test_refused_when_the_building_cant_work(self):
        match = helpers.new_match(self)
        build(match, "shop", 4, 2)
        match.stock["wood"] = 1
        uid = give(match, "p1", "work-any")
        with self.assertRaisesRegex(LobbyError, "needs 2 wood"):
            match.play("p1", uid, 4, 2)
        self.assertTrue(in_hand(match, uid))

    def test_targets_list_only_workable_buildings(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        build(match, "hut", 5, 3)
        done = build(match, "mill", 1, 3)
        done.worked = True
        uid = give(match, "p1", "work-any")
        self.assertEqual(match.private("p1")["targets"][str(uid)], {str(mill.uid): "+3 wood (stored)"})


class RepairCureTests(helpers.FixtureCase):
    def test_repair_costs_a_wood_per_ruined_tile(self):
        match = helpers.new_match(self)
        field = build(match, "field", 4, 3)
        field.ruined = {(4, 3), (5, 3)}
        match.stock["wood"] = 1
        uid = give(match, "p1", "mend")
        with self.assertRaisesRegex(LobbyError, "short of wood"):
            match.play("p1", uid, 4, 4)
        match.stock["wood"] = 3
        match.play("p1", uid, 4, 4)
        self.assertEqual((field.ruined, match.stock["wood"]), (set(), 1))
        with self.assertRaisesRegex(LobbyError, "isn't damaged"):
            match.play("p1", give(match, "p1", "mend"), 4, 4)

    def test_cure_costs_food_and_hurts_the_plague_sender(self):
        match = helpers.new_match(self)
        rat = helpers.foe(self, match, "rat")
        mill = build(match, "mill", 1, 1)
        mill.plague = rat.index
        uid = give(match, "p1", "remedy")
        match.stock["food"] = 1
        with self.assertRaisesRegex(LobbyError, "isn't plagued"):
            match.play("p1", uid, 3, 2)
        match.play("p1", uid, 1, 1)
        self.assertIsNone(mill.plague)
        self.assertEqual((match.stock["food"], rat.hp), (0, rat.max_hp - 1))

    def test_a_curing_building_cures_too(self):
        match = helpers.new_match(self)
        rat = helpers.foe(self, match, "rat")
        build(match, "mill", 1, 1).plague = rat.index
        build(match, "clinic", 4, 2)
        match.stock["food"] = 1
        match.play("p1", give(match, "p1", "work-any"), 4, 2)
        self.assertFalse(match.plagued())
        self.assertEqual(rat.hp, rat.max_hp - 1)


class CurseAndGainTests(helpers.FixtureCase):
    def curse(self, match, card, sender):
        uid = give(match, "p1", card)
        match.seats["p1"].hand[-1]["from"] = sender.index
        return uid

    def test_paying_a_curse_removes_it_and_may_hurt_its_sender(self):
        match = helpers.new_match(self)
        sender = helpers.foe(self, match, "sender")
        brute = helpers.foe(self, match, "brute")
        match.stock["gold"] = 5
        match.play("p1", self.curse(match, "note", sender))
        match.play("p1", self.curse(match, "note", brute))  # the brute can't be hurt by cards
        self.assertNotIn("note", owned(match))
        self.assertEqual(match.stock["gold"], 3)
        self.assertEqual((sender.hp, brute.hp), (sender.max_hp - 1, brute.max_hp))

    def test_curses_cant_be_played_without_paying(self):
        match = helpers.new_match(self)
        match.stock["food"] = 0
        uid = self.curse(match, "dread", helpers.foe(self, match, "brute"))
        with self.assertRaisesRegex(LobbyError, "short of food"):
            match.play("p1", uid)
        self.assertTrue(in_hand(match, uid))

    def test_gain_and_draw(self):
        match = helpers.new_match(self)
        gold, hand = match.stock["gold"], len(match.seats["p1"].hand)
        match.play("p1", give(match, "p1", "boon"))
        self.assertEqual((match.stock["gold"], match.soldiers), (gold + 2, 1))
        self.assertEqual(len(match.seats["p1"].hand), hand + 1)  # played one, drew one (+ the given card)


class MarketAndTurnTests(helpers.FixtureCase):
    def test_buy_with_team_gold_into_the_discard_pile(self):
        match = helpers.new_match(self)
        match.stock["gold"] = 1
        card = match.market.slots[0]
        match.buy("p1", 0)
        self.assertEqual(match.stock["gold"], 0)
        self.assertEqual(match.seats["p1"].deck.discard_pile[-1]["card"], card)
        with self.assertRaisesRegex(LobbyError, "short of gold"):
            match.buy("p1", 0)
        with self.assertRaisesRegex(LobbyError, "no such card"):
            match.buy("p1", 99)

    def test_done_players_cant_act_until_they_take_it_back(self):
        match = helpers.new_match(self, players=2)
        uid = give(match, "p1", "boon")
        match.end_turn("p1")
        with self.assertRaisesRegex(LobbyError, "ended your turn"):
            match.play("p1", uid)
        match.end_turn("p1", False)
        match.play("p1", uid)

    def test_cards_must_be_in_hand(self):
        match = helpers.new_match(self)
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            match.play("p1", 999)
        with self.assertRaisesRegex(LobbyError, "not in this game"):
            match.play("p9", 1)


if __name__ == "__main__":
    unittest.main()

"""Bastion: playing cards on fixture content (blueprints, repair, cure, curses, gains), units
working buildings, the market and whose turn it is, through Match.
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
    def test_build_pays_and_leaves_the_deck(self):
        match = helpers.new_match(self)
        match.stock["wood"] = 3
        uid = give(match, "p1", "plan-mill")
        match.play("p1", uid, 1, 1, 0)
        mill = match.board.structures[match.board.at[(1, 1)]]
        self.assertEqual((mill.kind, sorted(mill.cells)), ("mill", [(1, 1), (2, 1)]))
        self.assertEqual(match.stock["wood"], 2)
        self.assertNotIn("plan-mill", owned(match))
        self.assertIn("P1 built", match.log[-1]["text"])

    def test_rotation_is_used(self):
        match = helpers.new_match(self)
        match.play("p1", give(match, "p1", "plan-ell"), 4, 2, 1)
        self.assertEqual(sorted(match.board.structures[match.board.at[(4, 2)]].cells),
                         sorted(match.board.footprint("ell", 1, 4, 2)))

    def test_a_building_can_give_a_card(self):
        match = helpers.new_match(self)
        match.play("p1", give(match, "p1", "plan-hut"), 5, 3)
        self.assertIn("boon", [c["card"] for c in match.seats["p1"].deck.discard_pile])

    def test_refused_builds_change_nothing(self):
        match = helpers.new_match(self)
        match.stock["wood"] = 0
        mill = give(match, "p1", "plan-mill")
        with self.assertRaisesRegex(LobbyError, "short of wood"):
            match.play("p1", mill, 1, 1, 0)
        with self.assertRaisesRegex(LobbyError, "next to forest"):
            match.play("p1", mill, 4, 4, 0)
        with self.assertRaisesRegex(LobbyError, "Pick where"):
            match.play("p1", mill)
        self.assertTrue(in_hand(match, mill))
        self.assertEqual(list(match.board.structures), [1])  # just the keep


class UnitWorkTests(helpers.FixtureCase):
    def test_a_unit_works_its_building_once(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        helpers.put(match, "p1", f"s{mill.uid}")
        match.resolve("p1", f"s{mill.uid}")
        self.assertEqual(mill.store, {"wood": 3})
        self.assertEqual((match.placed, match.seats["p1"].spent), ({}, 1))
        with self.assertRaisesRegex(LobbyError, "no unit there"):
            match.resolve("p1", f"s{mill.uid}")

    def test_needs_a_worked_building(self):
        match = helpers.new_match(self, act=False)
        helpers.units(match, "p1", 2)
        hut = build(match, "hut", 5, 3)
        with self.assertRaisesRegex(LobbyError, "nothing there"):
            match.place("p1", "s99")
        with self.assertRaisesRegex(LobbyError, "isn't worked"):
            match.place("p1", f"s{hut.uid}")

    def test_refused_when_the_building_cant_work(self):
        match = helpers.new_match(self)
        shop = build(match, "shop", 4, 2)
        match.stock["wood"] = 1
        helpers.put(match, "p1", f"s{shop.uid}")
        with self.assertRaisesRegex(LobbyError, "needs 2 wood"):
            match.resolve("p1", f"s{shop.uid}")
        self.assertEqual(match.placed, {f"s{shop.uid}": {"p1": 1}})

    def test_places_list_only_open_buildings(self):
        match = helpers.new_match(self, players=2, act=False)
        helpers.units(match, "p1", 1)
        mill = build(match, "mill", 1, 1)
        build(match, "hut", 5, 3)
        taken = build(match, "mill", 1, 3)
        helpers.put(match, "p2", f"s{taken.uid}")
        places = match.private("p1")["places"]
        self.assertEqual(sorted(places), sorted(["haul", f"s{mill.uid}"]))
        self.assertEqual(places[f"s{mill.uid}"]["text"], "+3 wood (stored)")


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

    def test_cure_costs_wheat_and_hurts_the_plague_sender(self):
        match = helpers.new_match(self)
        rat = helpers.foe(self, match, "rat")
        mill = build(match, "mill", 1, 1)
        mill.plague = rat.index
        uid = give(match, "p1", "remedy")
        match.stock["wheat"] = 1
        with self.assertRaisesRegex(LobbyError, "isn't plagued"):
            match.play("p1", uid, 3, 2)
        match.play("p1", uid, 1, 1)
        self.assertIsNone(mill.plague)
        self.assertEqual((match.stock["wheat"], rat.hp), (0, rat.max_hp - 1))

    def test_a_curing_building_cures_too(self):
        match = helpers.new_match(self)
        rat = helpers.foe(self, match, "rat")
        build(match, "mill", 1, 1).plague = rat.index
        clinic = build(match, "clinic", 4, 2)
        match.stock["wheat"] = 1
        helpers.put(match, "p1", f"s{clinic.uid}")
        match.resolve("p1", f"s{clinic.uid}")
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
        match.stock["wheat"] = 0
        uid = self.curse(match, "dread", helpers.foe(self, match, "brute"))
        with self.assertRaisesRegex(LobbyError, "short of wheat"):
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

    def test_only_the_acting_player_plays(self):
        match = helpers.new_match(self, players=2, act=False)
        uid = give(match, "p2", "boon")
        with self.assertRaisesRegex(LobbyError, "Place your units first"):
            match.play("p2", uid)
        match.ready("p1")
        match.ready("p2")
        with self.assertRaisesRegex(LobbyError, "P1's turn"):
            match.play("p2", uid)
        match.end_turn("p1")
        match.play("p2", uid)

    def test_cards_must_be_in_hand(self):
        match = helpers.new_match(self)
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            match.play("p1", 999)
        with self.assertRaisesRegex(LobbyError, "not in this game"):
            match.play("p9", 1)


if __name__ == "__main__":
    unittest.main()

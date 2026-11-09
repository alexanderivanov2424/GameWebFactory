"""Bastion: economy rules on fixture content (output and bonuses, delivery, who can work).
Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

helpers = importlib.import_module("games.bastion.tests.helpers")
economy = importlib.import_module("games.bastion.logic.economy")
build = helpers.build


def output(match, s):
    return economy.output(match.board, s.kind, s.cells)


def why_not(match, s):
    return economy.why_not(match.board, s, match.stock, match.round, match.plagued())


class OutputTests(helpers.FixtureCase):
    def test_base_plus_met_conditions(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)  # next to 2 forest: +1
        self.assertEqual(output(match, mill), (3, [["base", 2], ["next to ≥2 forest", 1]]))
        build(match, "yard", 3, 1)
        self.assertEqual(output(match, mill)[0], 4)

    def test_penalties_and_blight(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        build(match, "mill", 1, 2)
        self.assertEqual(output(match, mill)[0], 2)
        match.board.add_blight((2, 0), "Grave", "", 0)
        amount, parts = output(match, mill)
        self.assertEqual(amount, 1)
        self.assertIn(["enemy blight next to it", -1], parts)

    def test_never_below_zero(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 5, 1)  # base 2, no forest
        for cell in ((4, 1), (5, 0), (6, 1)):
            match.board.add_blight(cell, "Grave", "", 0)
        self.assertEqual(output(match, mill)[0], 0)

    def test_per_neighbour_bonus_has_a_cap(self):
        match = helpers.new_match(self)
        field = build(match, "field", 4, 3)
        build(match, "hut", 3, 3)
        self.assertEqual(output(match, field)[0], 3)
        build(match, "hut", 3, 4)
        build(match, "hut", 4, 5)
        self.assertEqual(output(match, field)[0], 4)

    def test_preview_matches_targets(self):
        match = helpers.new_match(self)
        uid = helpers.give(match, "p1", "plan-mill")
        spots = match.private("p1")["targets"][str(uid)]["0"]
        self.assertEqual(spots["1,1"], 3)
        self.assertNotIn("4,3", spots)  # no forest there


class DeliveryTests(helpers.FixtureCase):
    def test_next_to_a_depot_goes_to_the_stockpile(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        build(match, "yard", 3, 1)
        wood = match.stock["wood"]
        self.assertEqual(economy.work(match.board, mill, match.stock), ("wood", 4, "stockpile"))
        self.assertEqual(match.stock["wood"], wood + 4)
        self.assertEqual(mill.store, {})

    def test_otherwise_stored_up_to_the_cap(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        wood = match.stock["wood"]
        self.assertEqual(economy.work(match.board, mill, match.stock), ("wood", 3, "stored"))
        self.assertEqual((mill.store, match.stock["wood"]), ({"wood": 3}, wood))
        mill.worked = False
        mill.store = {"wood": economy.STORE_CAP - 1}
        self.assertEqual(economy.work(match.board, mill, match.stock)[1], 1)
        self.assertEqual(mill.stored(), economy.STORE_CAP)

    def test_inputs_are_paid_from_the_stockpile(self):
        match = helpers.new_match(self)
        shop = build(match, "shop", 4, 2)
        match.stock.update(wood=3, tools=0)
        economy.work(match.board, shop, match.stock)
        self.assertEqual((match.stock["wood"], match.stock["tools"]), (1, 1))
        self.assertTrue(shop.worked)


class WhoCanWorkTests(helpers.FixtureCase):
    def test_once_per_round(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        self.assertIsNone(why_not(match, mill))
        mill.worked = True
        self.assertIn("already worked", why_not(match, mill))

    def test_damaged_plagued_or_frozen(self):
        match = helpers.new_match(self)
        mill = build(match, "mill", 1, 1)
        for setup, words in ((lambda: mill.ruined.add((1, 1)), "damaged"),
                             (lambda: setattr(mill, "plague", 0), "plagued"),
                             (lambda: setattr(mill, "frozen", match.round), "frozen")):
            mill.ruined, mill.plague, mill.frozen = set(), None, 0
            setup()
            self.assertIn(words, why_not(match, mill))
        mill.ruined, mill.plague, mill.frozen = set(), None, match.round + 1  # frozen next round only
        self.assertIsNone(why_not(match, mill))

    def test_inputs_need_a_link_and_stock(self):
        match = helpers.new_match(self)
        match.stock["wood"] = 5
        self.assertIn("cut off", why_not(match, build(match, "shop", 6, 3)))
        near_keep = build(match, "shop", 4, 2)
        self.assertIsNone(why_not(match, near_keep))
        match.stock["wood"] = 1
        self.assertIn("needs 2 wood", why_not(match, near_keep))

    def test_cures_need_a_plague(self):
        match = helpers.new_match(self)
        match.stock["food"] = 2
        clinic = build(match, "clinic", 4, 2)
        self.assertIn("Nothing is plagued", why_not(match, clinic))
        build(match, "mill", 1, 1).plague = 0
        self.assertIsNone(why_not(match, clinic))

    def test_not_worked_or_making_nothing(self):
        match = helpers.new_match(self)
        self.assertIn("isn't worked", why_not(match, build(match, "hut", 5, 3)))
        mill = build(match, "mill", 5, 1)
        for cell in ((4, 1), (5, 0), (6, 1)):
            match.board.add_blight(cell, "Grave", "", 0)
        self.assertIn("would make nothing", why_not(match, mill))


if __name__ == "__main__":
    unittest.main()

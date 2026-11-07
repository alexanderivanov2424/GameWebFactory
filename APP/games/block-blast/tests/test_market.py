"""Block Blast: the market (logic/market/): the Conveyor Market and the Cost Market on their own,
buying and removing through Match, and the lobby settings that pick the type and size.
Run: python3 -I tools/run_tests.py block-blast
"""

import importlib
import random
import unittest

from gamekit import LobbyError
from gamekit.sim import Sim

helpers = importlib.import_module("games.block-blast.tests.helpers")  # the id contains "-"
new_match = helpers.new_match
market = importlib.import_module("games.block-blast.logic.market")
CARDS = importlib.import_module("games.block-blast.logic.cards").CARDS


class RegistryTests(unittest.TestCase):
    def test_types_declare_what_the_lobby_needs(self):
        self.assertEqual(list(market.MARKETS), ["conveyor", "cost"])
        self.assertIn(market.DEFAULT, market.MARKETS)
        for kind, cls in market.MARKETS.items():
            self.assertEqual(cls.KEY, kind)
            self.assertTrue(cls.LABEL and cls.SIZE_SETTING and cls.RULES)
            self.assertTrue(1 <= cls.DEFAULT_SIZE <= cls.MAX_SIZE <= market.MAX_SIZE)

    def test_every_bonus_card_has_a_cost(self):
        for card_id, card in CARDS.items():
            self.assertIsInstance(card["cost"], int, card_id)
        self.assertEqual(CARDS["dagger"]["cost"], 5)  # 1 tile, +1 attack, +3 all symbols
        self.assertEqual(CARDS["crate"]["cost"], 9)  # 9 tiles, no attack


class ConveyorTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_prices_by_slot_and_empty_until_end_of_turn(self):
        stall = self.match.market
        seat = self.match.seats[self.me]
        seat.gold = 2
        with self.assertRaisesRegex(LobbyError, "costs 3 gold"):
            self.match.buy(self.me, 2)
        third = stall.slots[2]
        seat.gold = 5
        self.match.buy(self.me, 2)  # 3 gold
        self.assertEqual(seat.gold, 2)
        self.assertIsNone(stall.slots[2])
        self.assertEqual([c["card"] for c in seat.deck.discard_pile], [third["card"]])
        rest = [stall.slots[0], stall.slots[1], stall.slots[3], stall.slots[4]]
        left = len(stall.deck)
        self.match.end_turn(self.me)
        self.assertEqual(stall.slots[:4], rest)  # shifted towards slot 0
        self.assertTrue(all(stall.slots))
        self.assertEqual(len(stall.deck), left - 1)

    def test_one_buy_per_turn(self):
        seat = self.match.seats[self.me]
        seat.gold = 15
        self.match.buy(self.me, 0)
        self.assertEqual(self.match.public()["buysLeft"], 0)
        with self.assertRaisesRegex(LobbyError, "only buy 1 card a turn"):
            self.match.buy(self.me, 1)
        with self.assertRaisesRegex(LobbyError, "only buy 1"):
            self.match.buy(self.me, 0)  # the limit is checked before the empty slot
        self.assertEqual(seat.gold, 14)
        self.match.end_turn(self.me)
        self.assertEqual(self.match.public()["buysLeft"], 1)  # the next player's buy
        self.match.seats[self.other].gold = 5
        self.match.buy(self.other, 0)
        self.match.end_turn(self.other)
        self.match.buy(self.me, 0)  # a new turn, a new buy
        self.assertEqual(seat.gold, 13)

    def test_no_removing_and_no_such_slot(self):
        with self.assertRaisesRegex(LobbyError, "doesn't let you remove"):
            self.match.market_remove(self.me, 0)
        with self.assertRaisesRegex(LobbyError, "no such market slot"):
            self.match.buy(self.me, 5)

    def test_size_setting(self):
        match = new_match(conveyorSize=8, costSize=3)
        self.assertEqual(len(match.market.slots), 8)
        self.assertEqual([s["price"] for s in match.public()["market"]["slots"]], list(range(1, 9)))

    def test_bonus_deck_runs_out(self):
        stall = market.make("conveyor", 5, ["dagger"] * 7, random.Random(1), CARDS)  # 5 dealt, 2 left
        stall.take(0)
        stall.take(1)
        stall.refill()
        self.assertEqual(sum(1 for s in stall.slots if s), 5)
        stall.take(0)
        stall.take(4)
        stall.refill()
        self.assertEqual(sum(1 for s in stall.slots if s), 3)
        self.assertEqual(stall.slots[3:], [None, None])

    def test_bought_cards_have_own_uids(self):
        self.match.buy(self.me, 0)
        seat = self.match.seats[self.me]
        uids = [c["uid"] for c in seat.hand + seat.deck.draw_pile + seat.deck.discard_pile]
        self.assertEqual(len(uids), len(set(uids)))


class CostTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match(market="cost")
        self.me, self.other = self.match.order
        self.stall = self.match.market

    def test_size_and_prices_are_card_costs(self):
        self.assertEqual(len(self.stall.slots), 10)
        public = self.match.public()["market"]
        self.assertEqual((public["type"], public["label"], public["canRemove"]), ("cost", "Cost Market", True))
        self.assertEqual([s["price"] for s in public["slots"]], [CARDS[c["card"]]["cost"] for c in self.stall.slots])
        self.assertEqual(public["deck"], 49 - 10)
        self.assertEqual(len(new_match(market="cost", costSize=4).market.slots), 4)

    def test_buy_any_slot_for_its_cost(self):
        seat = self.match.seats[self.me]
        last = self.stall.slots[9]
        cost = CARDS[last["card"]]["cost"]
        seat.gold = cost - 1
        with self.assertRaisesRegex(LobbyError, f"costs {cost} gold"):
            self.match.buy(self.me, 9)
        seat.gold = cost
        self.match.buy(self.me, 9)
        self.assertEqual(seat.gold, 0)
        self.assertEqual([c["card"] for c in seat.deck.discard_pile], [last["card"]])

    def test_remove_uses_the_buy_and_leaves_the_game(self):
        seat = self.match.seats[self.me]
        seat.gold = 20
        removed = self.stall.slots[3]
        left = len(self.stall.deck)
        self.match.market_remove(self.me, 3)
        self.assertIsNone(self.stall.slots[3])
        self.assertEqual(seat.gold, 20)  # free
        self.assertEqual(seat.deck.discard_pile, [])  # not the player's
        self.assertIn("removed", self.match.log[-1]["text"])
        with self.assertRaisesRegex(LobbyError, r"only buy 1 card a turn \(removing one counts as a buy\)"):
            self.match.buy(self.me, 0)
        with self.assertRaisesRegex(LobbyError, "only buy 1"):
            self.match.market_remove(self.me, 0)
        others = self.stall.slots[:3] + self.stall.slots[4:]
        self.match.end_turn(self.me)
        self.assertEqual(self.stall.slots[:3] + self.stall.slots[4:], others)  # nothing shifts
        self.assertIsNotNone(self.stall.slots[3])  # refilled in place
        self.assertNotEqual(self.stall.slots[3]["uid"], removed["uid"])
        self.assertEqual(len(self.stall.deck), left - 1)

    def test_remove_refused(self):
        with self.assertRaisesRegex(LobbyError, "not your turn"):
            self.match.market_remove(self.other, 0)
        self.match.market_remove(self.me, 0)
        self.match.end_turn(self.me)
        self.match.seats[self.other].gold = 20
        self.match.buy(self.other, 1)
        with self.assertRaisesRegex(LobbyError, "only buy 1"):
            self.match.market_remove(self.other, 2)

    def test_refill_in_place_until_the_deck_runs_out(self):
        stall = market.make("cost", 4, ["dagger"] * 5, random.Random(1), CARDS)  # 4 dealt, 1 left
        stall.take(1)
        stall.take(2)
        stall.refill()
        self.assertEqual([s is not None for s in stall.slots], [True, True, False, True])
        self.assertIsNone(stall.price(2))


class LobbyMarketTests(unittest.TestCase):
    def test_settings_built_from_the_registry(self):
        sim = Sim(helpers.GAME, start=False)
        state = sim.state(0)
        self.assertEqual(state["settings"], helpers.SETTINGS)
        spec = {s["key"]: s for s in state["settingsSpec"]}
        self.assertEqual([o["label"] for o in spec["market"]["options"]], ["Conveyor Market", "Cost Market"])
        self.assertEqual((spec["costSize"]["min"], spec["costSize"]["max"]), (1, 20))
        self.assertIn("must be one of", sim.lobby(0, {"type": "settings", "settings": {"market": "bazaar"}}))
        sim.lobby(0, {"type": "settings", "settings": {"conveyorSize": 99}})
        self.assertEqual(sim.state(0)["settings"]["conveyorSize"], 10)  # clamped

    def test_cost_market_game(self):
        sim = Sim(helpers.GAME, players=2, settings={"market": "cost", "costSize": 6})
        first, second = [sim.index_of(pid) for pid in sim.game.match.queue.order()]
        public = sim.state(first)["game"]["market"]
        self.assertEqual((public["type"], len(public["slots"])), ("cost", 6))
        sim.fails(second, {"action": "market_remove", "slot": 0}, "not your turn")
        sim.fails(first, {"action": "market_remove", "slot": 6}, "no such market slot")
        sim.fails(first, {"action": "market_remove", "slot": "0"}, "whole number")
        sim.ok(first, {"action": "market_remove", "slot": 0})
        self.assertIsNone(sim.state(second)["game"]["market"]["slots"][0])
        self.assertEqual(sim.state(first)["game"]["buysLeft"], 0)

    def test_conveyor_game_refuses_remove(self):
        sim = Sim(helpers.GAME, players=2)
        first = sim.index_of(sim.game.match.turn())
        sim.fails(first, {"action": "market_remove", "slot": 0}, "doesn't let you remove")


if __name__ == "__main__":
    unittest.main()

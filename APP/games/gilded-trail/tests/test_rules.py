"""Gilded Trail: rule tests on Match. Each test builds an exact position (helpers.py) and
checks one rule; no games are played out.

Run: python3 -I tools/run_tests.py gilded-trail
"""

import importlib
import unittest

from gamekit import LobbyError

h = importlib.import_module("games.gilded-trail.tests.helpers")
movement = importlib.import_module("games.gilded-trail.logic.movement")
board = importlib.import_module("games.gilded-trail.logic.board")
CARDS = h.CARDS


class Base(unittest.TestCase):
    def setUp(self):
        self.m = h.new_match()
        self.pid = h.cur(self.m)
        self.other = h.other(self.m)

    def place(self, key, ei=0):
        h.put(self.m, self.pid, ei, key)

    def hand(self, *cards):
        return h.hand(self.m, self.pid, *cards)

    def move(self, to, uid=None, ei=0):
        self.m.move(self.pid, ei, to, uid)

    def fails(self, call, *args, text=""):
        with self.assertRaises(LobbyError) as ctx:
            call(*args)
        self.assertIn(text.lower(), str(ctx.exception).lower())

    def explorer(self, ei=0):
        return self.m.players[self.pid]["explorers"][ei]


class MovementCardTests(Base):
    def test_card_moves_over_several_spaces_of_its_kind(self):
        h.lane(self.m, ("machete", 1), ("machete", 2), ("machete", 1), ("machete", 1))
        self.place("-1,0")
        cleaver, = self.hand("great-cleaver")
        self.move("0,0", cleaver)
        self.assertEqual(self.m.moving["left"], 5)
        self.move("1,0")
        self.move("2,0")
        self.assertEqual(self.explorer(), "2,0")
        self.assertEqual(self.m.moving["left"], 2)

    def test_card_stops_when_its_value_runs_out(self):
        h.lane(self.m, ("machete", 1), ("machete", 1))
        self.place("-1,0")
        tracker, = self.hand("tracker")  # value 2
        self.move("0,0", tracker)
        self.move("1,0")
        self.fails(self.move, "2,0", text="Pick a movement card")

    def test_leftover_is_lost_when_switching_cards(self):
        h.lane(self.m, ("machete", 1), ("machete", 1), ("machete", 1))
        self.place("-1,0")
        cleaver, porter = self.hand("great-cleaver", "porter")
        self.move("0,0", cleaver)
        self.move("1,0", porter)  # new card: the cleaver's 5 left are dropped
        self.assertEqual(self.m.moving["uid"], porter)
        self.assertEqual(self.m.moving["left"], 0)
        self.fails(self.move, "2,0", text="Pick a movement card")
        self.assertEqual(self.explorer(), "1,0")

    def test_joker_locks_to_the_first_kind(self):
        h.lane(self.m, ("machete", 1), ("paddle", 1), ("machete", 1))
        self.place("-1,0")
        joker, = self.hand("wayfarer")  # value 2
        self.move("0,0", joker)
        self.assertEqual(self.m.moving["kind"], "machete")
        self.fails(self.move, "1,0", text="can't pay")
        self.assertEqual(self.explorer(), "0,0")

    def test_joker_can_start_on_any_kind(self):
        h.lane(self.m, ("paddle", 1), ("paddle", 1))
        self.place("-1,0")
        joker, = self.hand("wayfarer")
        self.move("0,0", joker)
        self.assertEqual(self.m.moving["kind"], "paddle")
        self.move("1,0")
        self.assertEqual(self.explorer(), "1,0")

    def test_card_cannot_move_a_second_explorer(self):
        h.lane(self.m, ("machete", 1), ("machete", 1), ("machete", 1), ("machete", 1))
        self.place("-1,0", 0)
        self.place("2,0", 1)
        cleaver, = self.hand("great-cleaver")
        self.move("0,0", cleaver, ei=0)
        self.fails(self.move, "3,0", None, 1, text="only one explorer")
        self.assertEqual(self.explorer(1), "2,0")

    def test_wrong_kind_is_rejected(self):
        h.lane(self.m, ("paddle", 1))
        self.place("-1,0")
        porter, = self.hand("porter")
        self.fails(self.move, "0,0", porter, text="can't pay")
        self.assertEqual(self.m.players[self.pid]["hand"], [{"uid": porter, "card": "porter"}])

    def test_too_low_value_is_rejected(self):
        h.lane(self.m, ("machete", 2))
        self.place("-1,0")
        porter, = self.hand("porter")
        self.fails(self.move, "0,0", porter, text="can't pay")

    def test_action_card_cannot_move(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0")
        naturalist, = self.hand("naturalist")
        self.fails(self.move, "0,0", naturalist, text="Action cards")

    def test_no_card_and_none_moving_is_rejected(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0")
        self.fails(self.move, "0,0", text="Pick a movement card")

    def test_card_not_in_hand_is_rejected(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0")
        self.hand("porter")
        self.fails(self.move, "0,0", 999, text="isn't in your hand")

    def test_occupied_space_is_rejected(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0")
        h.put(self.m, self.other, 0, "0,0")
        porter, = self.hand("porter")
        self.fails(self.move, "0,0", porter, text="Another explorer")

    def test_own_explorer_also_blocks(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0", 0)
        self.place("0,0", 1)
        porter, = self.hand("porter")
        self.fails(self.move, "0,0", porter, text="Another explorer")

    def test_mountain_is_rejected(self):
        h.lane(self.m, ("mountain", 0))
        self.place("-1,0")
        cleaver, = self.hand("great-cleaver")
        self.fails(self.move, "0,0", cleaver, text="Nobody can enter")

    def test_not_adjacent_is_rejected(self):
        h.lane(self.m, ("machete", 1), ("machete", 1))
        self.place("-1,0")
        porter, = self.hand("porter")
        self.fails(self.move, "1,0", porter, text="next to")

    def test_wrong_player_cannot_move(self):
        h.lane(self.m, ("machete", 1))
        h.put(self.m, self.other, 0, "-1,0")
        h.hand(self.m, self.other, "porter")
        self.fails(self.m.move, self.other, 0, "0,0", 101, text="not your turn")


class RubbleCampTests(Base):
    def setUp(self):
        super().setUp()
        self.place("-1,0")

    def test_rubble_discards_exactly_n_cards(self):
        h.lane(self.m, ("rubble", 2))
        a, b, c, d = self.hand("porter", "trader", "boatman", "porter")
        self.fails(self.m.pay, self.pid, 0, "0,0", [a], text="exactly 2")
        self.fails(self.m.pay, self.pid, 0, "0,0", [a, b, c], text="exactly 2")
        self.m.pay(self.pid, 0, "0,0", [a, b])
        self.assertEqual(self.explorer(), "0,0")
        self.assertEqual([c["uid"] for c in self.m.players[self.pid]["hand"]], [c, d])
        self.m.end_turn(self.pid, [])
        # the two paid cards are on the discard pile (the other cards in hand drew back to 4)
        self.assertEqual(h.discard_cards(self.m, self.pid), ["porter", "trader"])
        self.assertEqual(h.removed_cards(self.m, self.pid), [])

    def test_base_camp_removes_n_cards_from_the_game(self):
        h.lane(self.m, ("camp", 2))
        a, b, c = self.hand("porter", "trader", "boatman")
        self.m.pay(self.pid, 0, "0,0", [a, c])
        self.assertEqual(self.explorer(), "0,0")
        self.assertEqual(h.removed_cards(self.m, self.pid), ["boatman", "porter"])
        self.m.end_turn(self.pid, [])
        self.assertEqual(h.discard_cards(self.m, self.pid), [])

    def test_rubble_cannot_be_paid_with_a_movement_card(self):
        h.lane(self.m, ("rubble", 1))
        porter, = self.hand("porter")
        self.fails(self.move, "0,0", porter, text="costs cards")

    def test_machete_space_cannot_be_paid_by_discarding(self):
        h.lane(self.m, ("machete", 1))
        porter, = self.hand("porter")
        self.fails(self.m.pay, self.pid, 0, "0,0", [porter], text="movement card")

    def test_duplicate_or_missing_cards_rejected(self):
        h.lane(self.m, ("rubble", 2))
        a, b = self.hand("porter", "trader")
        self.fails(self.m.pay, self.pid, 0, "0,0", [a, a], text="exactly 2")
        self.fails(self.m.pay, self.pid, 0, "0,0", [a, 555], text="isn't in your hand")

    def test_single_use_card_discarded_for_rubble_stays_in_the_game(self):
        h.lane(self.m, ("rubble", 1))
        cleaver, = self.hand("great-cleaver")
        self.m.pay(self.pid, 0, "0,0", [cleaver])
        self.assertEqual(h.removed_cards(self.m, self.pid), [])
        self.m.end_turn(self.pid, [])
        self.assertEqual(h.discard_cards(self.m, self.pid), ["great-cleaver"])

    def test_single_use_card_used_for_movement_is_removed(self):
        h.lane(self.m, ("machete", 1))
        cleaver, = self.hand("great-cleaver")
        self.move("0,0", cleaver)
        self.assertEqual(h.removed_cards(self.m, self.pid), ["great-cleaver"])
        self.m.end_turn(self.pid, [])
        self.assertEqual(h.discard_cards(self.m, self.pid), [])

    def test_reusable_card_goes_to_discard_after_moving(self):
        h.lane(self.m, ("machete", 1))
        porter, = self.hand("porter")
        self.move("0,0", porter)
        self.m.end_turn(self.pid, [])
        self.assertEqual(h.discard_cards(self.m, self.pid), ["porter"])


class BlockadeTests(Base):
    def setUp(self):
        super().setUp()
        h.lane(self.m, ("machete", 1), ("machete", 1), ("machete", 1), ("machete", 1))
        h.set_hex(self.m, "4,0", "machete", 1)
        h.set_hex(self.m, "5,0", "machete", 1)
        self.place("3,0")

    def test_blockade_is_claimed_without_moving_and_card_continues(self):
        h.set_blockade(self.m, 0, "machete", 1)
        cleaver, = self.hand("great-cleaver")
        self.move("4,0", cleaver)
        self.assertEqual(self.explorer(), "3,0")
        self.assertEqual(self.m.taken, {0: self.pid})
        self.assertEqual(self.m.players[self.pid]["blockades"], [0])
        self.assertEqual(self.m.moving["left"], 5)
        self.move("4,0")  # the border is open now: an ordinary 1-value step
        self.assertEqual(self.explorer(), "4,0")
        self.assertEqual(self.m.moving["left"], 4)

    def test_blockade_needs_its_kind_and_value(self):
        h.set_blockade(self.m, 0, "paddle", 1)
        porter, = self.hand("porter")
        self.fails(self.move, "4,0", porter, text="can't pay")
        h.set_blockade(self.m, 0, "machete", 2)
        self.fails(self.move, "4,0", porter, text="can't pay")
        self.assertEqual(self.m.taken, {})

    def test_rubble_blockade_is_cleared_by_discarding(self):
        h.set_blockade(self.m, 0, "rubble", 2)
        a, b, c = self.hand("porter", "trader", "boatman")
        self.fails(self.move, "4,0", a, text="costs cards")
        self.m.pay(self.pid, 0, "4,0", [a, b])
        self.assertEqual(self.m.taken, {0: self.pid})
        self.assertEqual(self.explorer(), "3,0")
        self.assertEqual([x["uid"] for x in self.m.players[self.pid]["hand"]], [c])

    def test_claimed_blockade_is_no_longer_charged(self):
        h.set_blockade(self.m, 0, "paddle", 2)
        h.put(self.m, self.other, 0, "3,0")
        self.place("2,0")
        self.assertEqual(movement.requirement(self.m, self.other, 0, "4,0")["need"], "paddle")
        self.m.taken[0] = self.pid
        req = movement.requirement(self.m, self.other, 0, "4,0")
        self.assertEqual((req["need"], req["v"]), ("machete", 1))
        self.assertNotIn("blockade", req)

    def test_blockade_must_be_crossed_in_the_right_place_only(self):
        h.set_blockade(self.m, 0, "paddle", 3)
        self.place("2,0")
        porter, = self.hand("porter")
        self.move("3,0", porter)  # inside tile 0: no blockade
        self.assertEqual(self.explorer(), "3,0")
        self.assertEqual(self.m.taken, {})


class BuyTests(Base):
    def setUp(self):
        super().setUp()
        h.fill_market(self.m, "tracker", "riverboat", "sketch-artist", "bushwhacker", "great-cleaver", "gold-cache")

    def buy(self, card, *uids):
        self.m.buy(self.pid, card, list(uids))

    def test_non_coin_cards_pay_half(self):
        a, b, c = self.hand("porter", "porter", "boatman")
        self.fails(self.buy, "tracker", a, text="costs 1")  # tracker costs 1: one half is short
        self.buy("tracker", a, b)
        self.assertEqual(self.m.players[self.pid]["hand"], [{"uid": c, "card": "boatman"}])

    def test_coin_cards_pay_their_value(self):
        a, b = self.hand("trader", "porter")
        self.fails(self.buy, "riverboat", a, text="costs 2")
        c, d = self.hand("trader", "trader")
        self.buy("riverboat", c, d)

    def test_joker_pays_full_value(self):
        a, = self.hand("wayfarer")  # 2
        self.buy("riverboat", a)  # costs 2
        self.assertTrue(self.m.bought)
        self.assertEqual(self.m.market.supply["riverboat"], 2)

    def test_bought_card_goes_to_the_discard_pile(self):
        a, = self.hand("gold-cache")
        self.buy("tracker", a)
        self.assertIn("tracker", h.discard_cards(self.m, self.pid))
        self.assertEqual(self.m.market.supply["tracker"], 2)

    def test_one_buy_per_turn(self):
        a, b = self.hand("gold-cache", "gold-cache")
        self.buy("tracker", a)
        self.fails(self.buy, "tracker", b, text="one card per turn")

    def test_buy_resets_next_turn(self):
        a, = self.hand("gold-cache")
        self.buy("tracker", a)
        self.m.end_turn(self.pid, [])
        self.m.end_turn(self.other, [])
        self.assertFalse(self.m.bought)
        self.assertEqual(self.m.turn(), self.pid)

    def test_reserve_card_needs_an_empty_slot(self):
        a, = self.hand("gold-cache")
        self.fails(self.buy, "chronicler", a, text="Reserve cards")
        self.m.market.slots[3] = ""
        self.buy("chronicler", a)
        self.assertEqual(self.m.market.slots[3], "chronicler")  # fills the empty slot
        self.assertEqual(self.m.market.supply["chronicler"], 2)

    def test_reserve_buy_fills_only_one_of_several_empty_slots(self):
        self.m.market.slots[0] = ""
        self.m.market.slots[1] = ""
        a, = self.hand("gold-cache")
        self.buy("chronicler", a)
        self.assertEqual(self.m.market.slots.count(""), 1)
        self.assertIn("chronicler", self.m.market.slots)

    def test_sold_out_slot_empties(self):
        self.m.market.supply["tracker"] = 1
        a, = self.hand("gold-cache")
        self.buy("tracker", a)
        self.assertEqual(self.m.market.slots[0], "")
        self.assertEqual(self.m.market.supply["tracker"], 0)

    def test_sold_out_card_cannot_be_bought(self):
        self.m.market.supply["tracker"] = 0
        a, = self.hand("gold-cache")
        self.fails(self.buy, "tracker", a, text="sold out")

    def test_unknown_or_starting_card_cannot_be_bought(self):
        a, = self.hand("gold-cache")
        self.fails(self.buy, "porter", a, text="isn't for sale")
        self.fails(self.buy, "nothing", a, text="isn't for sale")

    def test_no_payment_is_rejected(self):
        self.hand("gold-cache")
        self.fails(self.buy, "tracker", text="Choose the cards")

    def test_single_use_coin_card_is_removed_when_spent(self):
        a, b = self.hand("gold-cache", "trader")
        self.buy("tracker", a)
        self.assertEqual(h.removed_cards(self.m, self.pid), ["gold-cache"])
        self.m.end_turn(self.pid, [])
        self.assertNotIn("gold-cache", h.discard_cards(self.m, self.pid))

    def test_single_use_joker_is_removed_but_plain_joker_is_discarded(self):
        a, = self.hand("airship")
        self.buy("tracker", a)
        self.assertEqual(h.removed_cards(self.m, self.pid), ["airship"])
        self.m.bought = False
        b, = self.hand("wayfarer")
        self.buy("tracker", b)
        self.m.end_turn(self.pid, [])
        self.assertIn("wayfarer", h.discard_cards(self.m, self.pid))

    def test_single_use_non_coin_card_paid_as_half_is_not_removed(self):
        a, b = self.hand("great-cleaver", "porter")  # cleaver pays 1/2 (not a coin card)
        self.buy("tracker", a, b)
        self.assertEqual(h.removed_cards(self.m, self.pid), [])


class ActionTests(Base):
    def test_naturalist_draws_then_removes_up_to_n(self):
        nat, a, b = self.hand("naturalist", "porter", "trader")
        self.m.play(self.pid, nat)
        self.assertEqual(len(self.m.players[self.pid]["hand"]), 3)  # 2 + 1 drawn
        self.assertEqual(self.m.pending, {"kind": "remove", "max": 1})
        self.fails(self.m.trash, self.pid, [a, b], text="at most 1")
        self.m.trash(self.pid, [a])
        self.assertIsNone(self.m.pending)
        self.assertEqual(h.removed_cards(self.m, self.pid), ["porter"])

    def test_removing_nothing_is_allowed(self):
        nat, a = self.hand("naturalist", "porter")
        self.m.play(self.pid, nat)
        self.m.trash(self.pid, [])
        self.assertIsNone(self.m.pending)
        self.assertEqual(h.removed_cards(self.m, self.pid), [])

    def test_field_journal_draws_two_removes_two_and_is_single_use(self):
        fj, a, b = self.hand("field-journal", "porter", "trader")
        self.m.play(self.pid, fj)
        self.assertEqual(len(self.m.players[self.pid]["hand"]), 4)
        self.assertEqual(self.m.pending, {"kind": "remove", "max": 2})
        self.m.trash(self.pid, [a, b])
        self.assertEqual(h.removed_cards(self.m, self.pid), ["field-journal", "porter", "trader"])

    def test_trash_cannot_remove_the_same_card_twice(self):
        nat, a = self.hand("field-journal", "porter")
        self.m.play(self.pid, nat)
        self.fails(self.m.trash, self.pid, [a, a], text="at most")

    def test_trash_without_pending_is_rejected(self):
        a, = self.hand("porter")
        self.fails(self.m.trash, self.pid, [a], text="nothing like that")

    def test_non_action_card_cannot_be_played(self):
        a, = self.hand("porter")
        self.fails(self.m.play, self.pid, a, text="Only action cards")

    def test_courier_takes_a_reserve_card_without_filling_a_slot(self):
        h.fill_market(self.m, "tracker", "riverboat", "sketch-artist", "bushwhacker", "great-cleaver", "gold-cache")
        before = list(self.m.market.slots)
        courier, = self.hand("courier")
        self.m.play(self.pid, courier)
        self.assertEqual(self.m.pending, {"kind": "free"})
        self.m.take(self.pid, "chronicler")  # a reserve card; no slot is empty
        self.assertEqual(self.m.market.slots, before)
        self.assertEqual(self.m.market.supply["chronicler"], 2)
        self.assertIn("chronicler", h.discard_cards(self.m, self.pid))
        self.assertFalse(self.m.bought)
        self.assertEqual(h.removed_cards(self.m, self.pid), ["courier"])

    def test_courier_can_take_a_market_card_and_empties_a_sold_out_slot(self):
        h.fill_market(self.m, "tracker")
        self.m.market.supply["tracker"] = 1
        courier, = self.hand("courier")
        self.m.play(self.pid, courier)
        self.m.take(self.pid, "tracker")
        self.assertEqual(self.m.market.slots[0], "")

    def test_courier_can_skip_and_cannot_take_sold_out_or_unknown(self):
        courier, = self.hand("courier")
        self.m.play(self.pid, courier)
        self.m.market.supply["chronicler"] = 0
        self.fails(self.m.take, self.pid, "chronicler", text="sold out")
        self.fails(self.m.take, self.pid, "porter", text="isn't for sale")
        self.m.take(self.pid, None)
        self.assertIsNone(self.m.pending)

    def test_courier_does_not_use_up_the_buy(self):
        h.fill_market(self.m, "tracker")
        courier, coin = self.hand("courier", "gold-cache")
        self.m.play(self.pid, courier)
        self.m.take(self.pid, "tracker")
        self.m.buy(self.pid, "tracker", [coin])

    def test_local_guide_ignores_the_requirement(self):
        h.lane(self.m, ("paddle", 3), ("mountain", 0))
        self.place("-1,0")
        guide, = self.hand("local-guide")
        self.m.play(self.pid, guide)
        self.assertEqual(self.m.pending, {"kind": "guide"})
        self.assertIn("0,0", self.m.private(self.pid)["guide"]["0"])
        self.m.guide(self.pid, 0, "0,0")
        self.assertEqual(self.explorer(), "0,0")
        self.assertIsNone(self.m.pending)

    def test_local_guide_cannot_enter_mountains_or_occupied_spaces(self):
        h.lane(self.m, ("mountain", 0), ("machete", 1))
        self.place("-1,0", 0)
        h.put(self.m, self.other, 0, "-2,0")
        guide, = self.hand("local-guide")
        self.m.play(self.pid, guide)
        self.fails(self.m.guide, self.pid, 0, "0,0", text="Nobody can enter")
        self.fails(self.m.guide, self.pid, 0, "-2,0", text="Another explorer")
        self.assertEqual(self.m.pending, {"kind": "guide"})  # still waiting for a good choice

    def test_local_guide_can_clear_a_blockade_without_moving(self):
        h.set_hex(self.m, "3,0", "machete", 1)
        h.set_hex(self.m, "4,0", "paddle", 3)
        h.set_blockade(self.m, 0, "coin", 4)
        self.place("3,0")
        guide, = self.hand("local-guide")
        self.m.play(self.pid, guide)
        self.m.guide(self.pid, 0, "4,0")
        self.assertEqual(self.explorer(), "3,0")
        self.assertEqual(self.m.taken, {0: self.pid})

    def test_local_guide_can_be_skipped(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0")
        guide, = self.hand("local-guide")
        self.m.play(self.pid, guide)
        self.m.guide(self.pid, 0, None)
        self.assertIsNone(self.m.pending)
        self.assertEqual(self.explorer(), "-1,0")

    def test_local_guide_needs_a_target(self):
        for ex, spot in enumerate(("-1,0", "-3,3")):  # every neighbour of both explorers is a mountain
            h.put(self.m, self.pid, ex, spot)
            for n in board.neighbors(spot):
                if n in self.m.board.hexes and n not in ("-1,0", "-3,3"):
                    h.set_hex(self.m, n, "mountain", 0)
        guide, = self.hand("local-guide")
        self.fails(self.m.play, self.pid, guide, text="space to step to")
        self.assertEqual(len(self.m.players[self.pid]["hand"]), 1)

    def test_pending_blocks_other_actions(self):
        h.lane(self.m, ("machete", 1))
        h.fill_market(self.m, "tracker")
        self.place("-1,0")
        nat, porter, coin = self.hand("naturalist", "porter", "gold-cache")
        self.m.play(self.pid, nat)
        self.fails(self.move, "0,0", porter, text="Finish the card")
        self.fails(self.m.pay, self.pid, 0, "0,0", [porter], text="Finish the card")
        self.fails(self.m.buy, self.pid, "tracker", [coin], text="Finish the card")
        self.fails(self.m.play, self.pid, porter, text="Finish the card")
        self.fails(self.m.end_turn, self.pid, [], text="Finish the card")
        self.fails(self.m.take, self.pid, None, text="nothing like that")
        self.m.trash(self.pid, [])
        self.move("0,0", porter)

    def test_action_card_goes_to_discard_unless_single_use(self):
        nat, = self.hand("naturalist")
        self.m.play(self.pid, nat)
        self.m.trash(self.pid, [])
        self.m.end_turn(self.pid, [])
        self.assertIn("naturalist", h.discard_cards(self.m, self.pid))


class EndTurnTests(Base):
    def test_discards_played_and_chosen_cards_and_draws_to_four(self):
        h.lane(self.m, ("machete", 1))
        self.place("-1,0")
        porter, a, b, c, d = self.hand("porter", "trader", "trader", "boatman", "porter")
        self.move("0,0", porter)
        self.m.end_turn(self.pid, [a])
        player = self.m.players[self.pid]
        self.assertEqual(len(player["hand"]), 4)
        self.assertEqual(h.discard_cards(self.m, self.pid), ["porter", "trader"])
        self.assertEqual({b, c, d} - {x["uid"] for x in player["hand"]}, set())  # kept cards stay
        self.assertEqual(self.m.played, [])

    def test_no_draw_when_hand_is_full(self):
        self.hand("porter", "porter", "porter", "porter", "trader")
        deck = len(self.m.players[self.pid]["deck"])
        self.m.end_turn(self.pid, [])
        self.assertEqual(len(self.m.players[self.pid]["hand"]), 5)
        self.assertEqual(len(self.m.players[self.pid]["deck"]), deck)

    def test_end_turn_rejects_cards_not_in_hand_and_duplicates(self):
        a, = self.hand("porter")
        self.fails(self.m.end_turn, self.pid, [999], text="isn't in your hand")
        self.fails(self.m.end_turn, self.pid, [a, a], text="each card")
        self.assertEqual(self.m.turn(), self.pid)

    def test_turn_passes_to_the_next_player(self):
        self.m.end_turn(self.pid, [])
        self.assertEqual(self.m.turn(), self.other)
        self.assertEqual(self.m.turn_number, 2)

    def test_discard_pile_is_reshuffled_when_the_deck_runs_out(self):
        player = self.m.players[self.pid]
        self.hand()
        player["deck"].discard(player["deck"].draw_pile)
        player["deck"].draw_pile = []
        self.m.end_turn(self.pid, [])
        self.assertEqual(len(player["hand"]), 4)

    def test_round_counter(self):
        self.assertEqual(self.m.round, 1)
        self.m.end_turn(self.pid, [])
        self.assertEqual(self.m.round, 1)
        self.m.end_turn(self.other, [])
        self.assertEqual(self.m.round, 2)
        self.assertEqual(self.m.turn(), self.pid)


class ArrivalTests(unittest.TestCase):
    def test_arriving_removes_the_explorer(self):
        m = h.new_match(3)
        pid = h.cur(m)
        h.lane(m, ("machete", 1), ("machete", 1))
        h.goal(m, "1,0")
        h.put(m, pid, 0, "0,0")
        porter, = h.hand(m, pid, "porter")
        m.move(pid, 0, "1,0", porter)
        self.assertEqual(m.players[pid]["explorers"], [""])
        self.assertEqual(m.players[pid]["arrived"], m.turn_number)
        self.assertTrue(m.final_round)
        self.assertIsNone(m.moving)  # the card's leftover can't be used elsewhere

    def test_arrived_explorer_cannot_move_again(self):
        m = h.new_match(3)
        pid = h.cur(m)
        h.goal(m, "1,0")
        h.set_hex(m, "0,0", "machete", 1)
        h.put(m, pid, 0, "0,0")
        a, b = h.hand(m, pid, "porter", "porter")
        m.move(pid, 0, "1,0", a)
        with self.assertRaises(LobbyError) as ctx:
            m.move(pid, 0, "0,0", b)
        self.assertIn("already arrived", str(ctx.exception))

    def test_two_player_game_needs_both_explorers(self):
        m = h.new_match(2)
        pid = h.cur(m)
        self.assertEqual(len(m.players[pid]["explorers"]), 2)
        h.lane(m, ("machete", 1), ("machete", 1), ("machete", 1))
        h.goal(m, "1,0")
        h.goal(m, "2,0")
        h.put(m, pid, 0, "0,0")
        h.put(m, pid, 1, "3,0")
        h.set_hex(m, "3,0", "machete", 1)
        a, b = h.hand(m, pid, "porter", "porter")
        m.move(pid, 0, "1,0", a)
        self.assertNotIn("arrived", m.players[pid])
        self.assertFalse(m.final_round)
        m.move(pid, 1, "2,0", b)
        self.assertEqual(m.players[pid]["arrived"], m.turn_number)
        self.assertTrue(m.final_round)

    def test_two_players_get_two_explorers_each_on_different_starts(self):
        m = h.new_match(2)
        spots = [e for p in m.players.values() for e in p["explorers"]]
        self.assertEqual(len(spots), 4)
        self.assertEqual(len(set(spots)), 4)
        self.assertTrue(set(spots) <= set(m.board.starts))

    def test_three_players_get_one_explorer_each(self):
        m = h.new_match(3)
        self.assertEqual([len(p["explorers"]) for p in m.players.values()], [1, 1, 1])


class EndOfGameTests(unittest.TestCase):
    def arrive(self, m, pid):
        h.lane(m, ("machete", 1), ("machete", 1))
        h.goal(m, "1,0")
        h.put(m, pid, 0, "0,0")
        porter, = h.hand(m, pid, "porter")
        m.move(pid, 0, "1,0", porter)

    def test_final_round_gives_everyone_equal_turns(self):
        m = h.new_match(3)
        first, second, third = m.seats
        m.end_turn(first, [])
        self.arrive(m, second)
        self.assertTrue(m.final_round)
        m.end_turn(second, [])
        self.assertIsNone(m.result)  # the third player still has a turn
        self.assertEqual(m.turn(), third)
        m.end_turn(third, [])
        self.assertEqual(m.result["winners"], [second])
        self.assertEqual(m.result["winner"], second)
        self.assertIsNone(m.turn())
        self.assertIn("final round", m.result["reason"])

    def test_arriving_first_in_the_round_lets_the_others_play(self):
        m = h.new_match(3)
        first, second, third = m.seats
        self.arrive(m, first)
        m.end_turn(first, [])
        m.end_turn(second, [])
        self.assertIsNone(m.result)
        m.end_turn(third, [])
        self.assertEqual(m.result["winner"], first)

    def test_later_arrivals_in_the_final_round_are_ranked(self):
        m = h.new_match(3)
        first, second, third = m.seats
        self.arrive(m, first)
        m.players[second]["blockades"] = [0]
        m.end_turn(first, [])
        self.arrive(m, second)
        m.end_turn(second, [])
        m.end_turn(third, [])
        self.assertEqual(m.result["winner"], second)  # a blockade beats arriving earlier

    def test_nobody_wins_if_nobody_arrives(self):
        m = h.new_match(3)
        m.end("stalled")
        self.assertEqual(m.result["winners"], [])
        self.assertIsNone(m.result["winner"])

    def test_moves_after_the_game_are_rejected(self):
        m = h.new_match(2)
        pid = h.cur(m)
        m.end("done")
        with self.assertRaises(LobbyError):
            m.end_turn(pid, [])


class TieBreakTests(unittest.TestCase):
    def setUp(self):
        self.m = h.new_match(3)
        self.a, self.b, self.c = self.m.seats
        for pid in self.m.seats:
            self.m.players[pid]["arrived"] = 10
        for i, v in enumerate((1, 2, 3, 1)):
            self.m.board.blockades[i]["v"] = v if i < len(self.m.board.blockades) else 1

    def set(self, pid, blockades, arrived):
        self.m.players[pid]["blockades"] = blockades
        self.m.players[pid]["arrived"] = arrived

    def winners(self):
        self.m.result = None
        self.m.end("test")
        return self.m.result["winners"]

    def test_most_blockades_wins(self):
        self.set(self.a, [0, 1], 5)  # two small
        self.set(self.b, [2], 3)     # one big, earlier
        self.set(self.c, [], 1)
        self.assertEqual(self.winners(), [self.a])

    def test_highest_blockade_breaks_a_tie(self):
        self.set(self.a, [0, 1], 5)  # values 1, 2
        self.set(self.b, [0, 2], 9)  # values 1, 3: higher, but arrived later
        self.set(self.c, [], 1)
        self.assertEqual(self.winners(), [self.b])

    def test_earliest_arrival_breaks_the_last_tie(self):
        self.set(self.a, [1], 7)
        self.set(self.b, [1], 4)
        self.set(self.c, [], 1)
        self.assertEqual(self.winners(), [self.b])

    def test_only_arrived_players_count(self):
        self.set(self.a, [0, 1, 2], 1)
        del self.m.players[self.a]["arrived"]
        self.set(self.b, [], 5)
        del self.m.players[self.c]["arrived"]
        self.assertEqual(self.winners(), [self.b])

    def test_players_who_left_never_win(self):
        self.set(self.a, [0, 1, 2], 1)
        self.m.players[self.a]["left"] = True
        self.set(self.b, [], 5)
        self.assertEqual(self.winners(), [self.b])

    def test_exact_tie_is_shared(self):
        self.set(self.a, [1], 4)
        self.set(self.b, [1], 4)
        self.set(self.c, [], 4)
        self.assertEqual(sorted(self.winners()), sorted([self.a, self.b]))
        self.assertIsNone(self.m.result["winner"])


class LeavingTests(unittest.TestCase):
    def test_last_remaining_player_wins(self):
        m = h.new_match(2)
        me, other = m.seats
        m.remove(other)
        self.assertEqual(m.result["winner"], me)
        self.assertEqual(m.result["winners"], [me])
        self.assertTrue(m.players[other]["left"])
        self.assertEqual(m.players[other]["explorers"], ["", ""])

    def test_leaving_on_own_turn_passes_the_turn(self):
        m = h.new_match(3)
        first, second, third = m.seats
        m.remove(first)
        self.assertIsNone(m.result)
        self.assertEqual(m.turn(), second)
        self.assertNotIn(first, m.queue)

    def test_leaving_off_turn_keeps_the_turn(self):
        m = h.new_match(3)
        first, second, third = m.seats
        m.remove(third)
        self.assertEqual(m.turn(), first)
        self.assertIsNone(m.result)

    def test_leaving_clears_pending_choices_of_the_old_turn(self):
        m = h.new_match(3)
        first = m.seats[0]
        h.hand(m, first, "naturalist")
        m.play(first, 101)
        self.assertIsNotNone(m.pending)
        m.remove(first)
        self.assertIsNone(m.pending)
        self.assertEqual(m.played, [])

    def test_leaving_player_cannot_win_and_blocks_nobody(self):
        m = h.new_match(3)
        first, second, third = m.seats
        m.remove(first)
        self.assertNotIn(first, m.public()["turnOrder"])
        self.assertTrue(m.public()["players"][first]["left"])
        self.assertEqual(h.cur(m), second)
        m.end_turn(second, [])
        m.end_turn(third, [])
        self.assertIsNone(m.result)

    def test_round_counter_ignores_a_leave_at_the_start_of_a_round(self):
        # The leaver's turn ends via next_turn(); equal turn counts for the remaining players
        # must not end a round that nobody has played yet.
        m = h.new_match(3)
        first, second, third = m.seats
        m.remove(first)
        self.assertEqual(m.round, 1)

    def test_leaving_completes_the_final_round(self):
        m = h.new_match(3)
        first, second, third = m.seats
        m.end_turn(first, [])
        h.lane(m, ("machete", 1), ("machete", 1))
        h.goal(m, "1,0")
        h.put(m, second, 0, "0,0")
        h.hand(m, second, "porter")
        m.move(second, 0, "1,0", 101)
        m.end_turn(second, [])
        m.remove(third)  # the only player who hadn't had a turn leaves: the round is over
        self.assertEqual(m.result["winner"], second)

    def test_leaving_twice_is_harmless(self):
        m = h.new_match(3)
        m.remove(m.seats[2])
        m.remove(m.seats[2])
        self.assertIsNone(m.result)

    def test_public_and_private_state_are_serialisable_shapes(self):
        m = h.new_match(2)
        pid = h.cur(m)
        self.assertEqual(m.public()["turn"], pid)
        self.assertEqual(len(m.private(pid)["hand"]), 4)
        self.assertIsNone(m.private("nobody"))

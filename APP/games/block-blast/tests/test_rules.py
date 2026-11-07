"""Block Blast: rules tests on logic.Match directly (setup, placing, clearing, aiming, turns,
leaving). Symbol effects are in test_effects.py, the market in test_market.py, the lobby side
in test_lobby.py.
Run: python3 -I tools/run_tests.py block-blast
"""

import importlib
import random
import unittest

from gamekit import LobbyError

helpers = importlib.import_module("games.block-blast.tests.helpers")  # the id contains "-"
new_match, give, cell, rows, fill = helpers.new_match, helpers.give, helpers.cell, helpers.rows, helpers.fill
row_cells, col_cells = helpers.row_cells, helpers.col_cells


class SetupTests(unittest.TestCase):
    def test_starting_hands_and_market(self):
        match = new_match(players=3)
        for place, pid in enumerate(match.order):
            seat = match.seats[pid]
            self.assertEqual(len(seat.hand), 3)
            self.assertEqual(len(seat.deck), 3)
            self.assertEqual(seat.health, 10)
            self.assertEqual(seat.gold, place + 1)  # 1 for the first player, 2, 3
        self.assertEqual(len(match.market.slots), 5)  # the default: a Conveyor Market of 5
        self.assertTrue(all(match.market.slots))
        self.assertEqual(len(match.market.deck), 49 - 5)

    def test_initial_targets_are_next_in_order(self):
        match = new_match(players=3)
        a, b, c = match.order
        self.assertEqual(match.seats[a].target, b)
        self.assertEqual(match.seats[c].target, a)
        self.assertEqual(match.turn(), a)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_place_rotated_shape(self):
        uid = give(self.match, self.me, "hook")  # "#." "#." "A#"
        self.match.place(self.me, uid, 1, 0, 0)  # one turn clockwise: "A##" "#.."
        view = rows(self.match.seats[self.me].board)
        self.assertEqual(view[0][:3], "A##")
        self.assertEqual(view[1][:3], "#..")
        self.assertNotIn(uid, [c["uid"] for c in self.match.seats[self.me].hand])
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me].deck.discard_pile])

    def test_off_board_overlap_and_unknown_card_refused(self):
        uid = give(self.match, self.me, "bar-4")
        with self.assertRaisesRegex(LobbyError, "doesn't fit"):
            self.match.place(self.me, uid, 0, 0, 6)  # columns 6..9
        fill(self.match, self.me, [(4, 4)])
        with self.assertRaisesRegex(LobbyError, "doesn't fit"):
            self.match.place(self.me, uid, 1, 2, 4)  # vertical over (4, 4)
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            self.match.place(self.me, 999, 0, 0, 0)
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me].hand])  # unchanged

    def test_not_your_turn(self):
        uid = give(self.match, self.other, "dagger")
        with self.assertRaisesRegex(LobbyError, "not your turn"):
            self.match.place(self.other, uid, 0, 0, 0)

    def test_patch_places_blank_tile(self):
        uid = give(self.match, self.me, "great-cross")
        self.match.patch(self.me, uid, 8, 8)
        self.assertEqual(self.match.seats[self.me].board[8][8], ("blue", None))
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me].deck.discard_pile])

    def test_multiple_cards_per_turn(self):
        hand = [c["uid"] for c in self.match.seats[self.me].hand]
        for i, uid in enumerate(hand):
            self.match.patch(self.me, uid, i, 0)
        self.assertEqual(self.match.seats[self.me].hand, [])
        self.assertEqual(self.match.turn(), self.me)


class ClearingTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_row_clear_gives_gold_and_damage(self):
        fill(self.match, self.me, row_cells(3, skip=(0, 1)))
        fill(self.match, self.me, [(3, 5)], "C")
        fill(self.match, self.me, [(3, 6)], "A")
        fill(self.match, self.me, [(4, 4)])  # not in the row: stays
        uid = give(self.match, self.me, "pair")  # "CA"
        seat = self.match.seats[self.me]
        gold = seat.gold
        self.match.place(self.me, uid, 0, 3, 0)
        self.assertEqual(seat.gold, gold + 2)
        self.assertEqual(self.match.seats[self.other].health, 8)
        self.assertEqual(rows(seat.board)[3], "." * 9)
        self.assertEqual(seat.board[4][4], ("blue", None))
        self.assertEqual(len(self.match.last_clear["cells"]), 9)

    def test_row_and_column_share_a_cell_once(self):
        # Row 0 and column 0 both complete when (0, 0) is filled; it holds an attack.
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        fill(self.match, self.me, col_cells(0, skip=(0,)))
        uid = give(self.match, self.me, "dagger")
        self.match.place(self.me, uid, 0, 0, 0)
        self.assertEqual(self.match.seats[self.other].health, 9)  # 1 attack, not 2
        self.assertEqual(len(self.match.last_clear["cells"]), 17)
        self.assertTrue(all(c is None for row in self.match.seats[self.me].board for c in row))

    def test_two_rows_at_once(self):
        fill(self.match, self.me, row_cells(0, skip=(0,)) + row_cells(1, skip=(0,)))
        uid = give(self.match, self.me, "bar-2")
        self.match.place(self.me, uid, 1, 0, 0)  # vertical bar in column 0
        self.assertIn("2 rows", self.match.log[-1]["text"])

    def test_knock_out_ends_two_player_game(self):
        self.match.seats[self.other].health = 1
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        uid = give(self.match, self.me, "dagger")
        self.match.place(self.me, uid, 0, 0, 0)
        self.assertEqual(self.match.seats[self.other].health, 0)
        self.assertEqual(self.match.result["winner"], self.me)
        self.assertIsNone(self.match.turn())


class AimTests(unittest.TestCase):
    def test_aim_and_reaim_after_knock_out(self):
        match = new_match(players=3)
        a, b, c = match.order
        match.aim(a, c)
        self.assertEqual(match.seats[a].target, c)
        match.aim(b, a)  # off-turn aiming is allowed
        with self.assertRaises(LobbyError):
            match.aim(a, a)
        with self.assertRaises(LobbyError):
            match.aim(a, "p9")
        # One attack on a cleared row: c drops to 1.
        match.seats[c].health = 2
        fill(match, a, row_cells(0, skip=(0,)))
        match.seats[a].board[0][1] = cell("A")
        match.place(a, give(match, a, "bar-2"), 1, 0, 0)  # vertical: completes row 0 only
        self.assertEqual(match.seats[c].health, 1)
        # A second one knocks c out; a re-aims at the next player still in (b).
        fill(match, a, row_cells(2, skip=(0,)), "A")
        match.patch(a, give(match, a, "dagger"), 2, 0)
        self.assertTrue(match.seats[c].out)
        self.assertEqual(match.seats[a].target, b)
        self.assertNotIn(c, match.queue)
        self.assertIsNone(match.result)
        with self.assertRaisesRegex(LobbyError, "still in"):
            match.aim(b, c)
        with self.assertRaisesRegex(LobbyError, "out of the game"):
            match.aim(c, a)


class TurnTests(unittest.TestCase):
    def test_end_turn_draws_to_three_and_reshuffles(self):
        match = new_match()
        me, other = match.order
        seat = match.seats[me]
        # Play the whole hand as patches on distinct cells.
        for i, uid in enumerate([c["uid"] for c in seat.hand]):
            match.patch(me, uid, 5, i)
        match.end_turn(me)
        self.assertEqual(len(seat.hand), 3)
        self.assertEqual(len(seat.deck), 0)
        self.assertEqual(match.turn(), other)
        match.end_turn(other)
        for i, uid in enumerate([c["uid"] for c in seat.hand]):
            match.patch(me, uid, 6, i)
        match.end_turn(me)  # draw pile empty: the 6 discards are reshuffled
        self.assertEqual(len(seat.hand), 3)
        self.assertEqual(len(seat.deck), 3)
        self.assertEqual(len(seat.deck.discard_pile), 0)

    def test_unplayed_cards_stay(self):
        match = new_match()
        me, _ = match.order
        hand = list(match.seats[me].hand)
        match.end_turn(me)
        self.assertEqual(match.seats[me].hand, hand)

    def test_leaving_on_own_turn_passes_turn_and_refills_market(self):
        match = new_match(players=3)
        a, b, c = match.order
        match.buy(a, 0)
        match.leave(a)
        self.assertEqual(match.turn(), b)
        self.assertTrue(all(match.market.slots))
        self.assertEqual(match.seats[c].target, b)
        self.assertIsNone(match.result)
        match.leave(c)
        self.assertEqual(match.result["winner"], b)

    def test_leaving_off_turn(self):
        match = new_match(players=3)
        a, b, c = match.order
        match.leave(b)
        self.assertEqual(match.turn(), a)
        self.assertEqual(match.seats[a].target, c)
        match.end_turn(a)
        self.assertEqual(match.turn(), c)


class StateTests(unittest.TestCase):
    def test_public_and_private(self):
        match = new_match()
        me, other = match.order
        public = match.public()
        self.assertEqual(public["rules"]["patch"], {"tiles": ["b"], "symbols": ["."]})
        self.assertEqual(public["rules"]["handSize"], 3)
        self.assertIn("hook", public["cards"])
        self.assertEqual(public["seats"][me]["hand"], 3)
        self.assertEqual(public["seats"][me]["draw"], 3)
        self.assertEqual(public["seats"][me]["board"]["tiles"], ["." * 9] * 9)
        private = match.private(me)
        self.assertEqual([c["uid"] for c in private["hand"]], [c["uid"] for c in match.seats[me].hand])
        self.assertEqual(private["drawPile"], sorted(private["drawPile"]))
        self.assertIsNone(match.private("p9"))

    def test_off_turn_actions_go_through_match(self):
        match = new_match()
        me, other = match.order
        for action in (lambda: match.buy(other, 0), lambda: match.end_turn(other),
                       lambda: match.patch(other, match.seats[other].hand[0]["uid"], 0, 0)):
            with self.assertRaisesRegex(LobbyError, "not your turn"):
                action()
        match.aim(other, me)  # allowed any time
        match.end(me, "test")
        with self.assertRaisesRegex(LobbyError, "game is over"):
            match.aim(other, me)


if __name__ == "__main__":
    unittest.main()

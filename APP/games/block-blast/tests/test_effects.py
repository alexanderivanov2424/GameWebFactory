"""Block Blast: what clears do, on logic.Match: shields, chapels (card removal), goblins
(spoiled lines, grey tiles), siege and strength. Run: python3 -I tools/run_tests.py block-blast
"""

import importlib
import unittest

from gamekit import LobbyError

helpers = importlib.import_module("games.block-blast.tests.helpers")  # the id contains "-"
effects = importlib.import_module("games.block-blast.logic.effects")
new_match, give, cell, rows, fill = helpers.new_match, helpers.give, helpers.cell, helpers.rows, helpers.fill
row_cells, col_cells = helpers.row_cells, helpers.col_cells


class ShieldTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def clear_row(self, pid, letters):
        """Row 0 of pid's board: `letters`, then blanks, then a patch at (0, 8) completes it."""
        cells = row_cells(0, skip=(8,))
        for (r, c), letter in zip(cells, letters + "#" * len(cells)):
            self.match.seats[pid].board[r][c] = cell(letter)
        self.match.patch(pid, give(self.match, pid, "bar-2"), 0, 8)

    def test_clearing_shields_adds_shield(self):
        self.clear_row(self.me, "SS")
        self.assertEqual(self.match.seats[self.me].shield, 2)
        self.assertIn("+2 shield", self.match.log[-1]["text"])

    def test_shield_absorbs_damage_and_is_used_up(self):
        defender = self.match.seats[self.other]
        defender.shield = 2
        self.clear_row(self.me, "AAA")
        self.assertEqual(defender.shield, 0)
        self.assertEqual(defender.health, 9)  # 3 attacks - 2 blocked
        self.assertIn("2 blocked", self.match.log[-1]["text"])

    def test_shield_bigger_than_attack(self):
        defender = self.match.seats[self.other]
        defender.shield = 3
        self.clear_row(self.me, "A")
        self.assertEqual((defender.shield, defender.health), (2, 10))

    def test_shield_decays_at_start_of_own_turn_only(self):
        mine, theirs = self.match.seats[self.me], self.match.seats[self.other]
        mine.shield, theirs.shield = 3, 3
        self.match.end_turn(self.me)  # other's turn starts
        self.assertEqual((mine.shield, theirs.shield), (3, 2))
        self.match.end_turn(self.other)  # my turn starts
        self.assertEqual((mine.shield, theirs.shield), (2, 2))
        mine.shield = 0
        self.match.end_turn(self.me)
        self.match.end_turn(self.other)
        self.assertEqual(mine.shield, 0)  # never below 0

    def test_shield_does_not_stop_knock_out(self):
        defender = self.match.seats[self.other]
        defender.shield, defender.health = 1, 1
        self.clear_row(self.me, "AA")
        self.assertEqual(defender.health, 0)
        self.assertEqual(self.match.result["winner"], self.me)


class ChapelTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_clearing_chapel_gives_removal(self):
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        self.match.seats[self.me].board[0][3] = cell("R")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(self.match.seats[self.me].chapels, 1)
        self.assertIn("+1 card removal", self.match.log[-1]["text"])

    def test_remove_card_leaves_deck_for_good(self):
        seat = self.match.seats[self.other]  # off-turn: allowed any time
        seat.chapels = 1
        card = seat.hand[0]
        total = len(seat.hand) + len(seat.deck) + len(seat.deck.discard_pile)
        self.match.remove_card(self.other, card["uid"])
        self.assertEqual(seat.chapels, 0)
        self.assertNotIn(card, seat.hand)
        self.assertNotIn(card, seat.deck.discard_pile)
        self.assertNotIn(card, seat.deck.draw_pile)
        self.assertEqual(len(seat.hand) + len(seat.deck) + len(seat.deck.discard_pile), total - 1)
        self.assertIn("removed", self.match.log[-1]["text"])

    def test_remove_refused(self):
        seat = self.match.seats[self.me]
        with self.assertRaisesRegex(LobbyError, "no card removals"):
            self.match.remove_card(self.me, seat.hand[0]["uid"])
        seat.chapels = 1
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            self.match.remove_card(self.me, 999)
        self.assertEqual(seat.chapels, 1)  # not spent on a refusal
        seat.out = True
        with self.assertRaisesRegex(LobbyError, "out of the game"):
            self.match.remove_card(self.me, seat.hand[0]["uid"])


class GoblinTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match(players=3)
        self.me, self.other, self.third = self.match.order

    def test_goblin_goes_on_opponent_board_and_leaves_my_deck(self):
        uid = give(self.match, self.me, "goblin-siege")  # 4 corners of a 3x3
        self.match.place(self.me, uid, 0, 2, 2, self.other)
        board_rows = rows(self.match.seats[self.other].board)
        self.assertEqual((board_rows[2][2], board_rows[2][4], board_rows[4][2], board_rows[4][4]), ("G",) * 4)
        self.assertEqual(rows(self.match.seats[self.me].board), ["." * 9] * 9)
        deck = self.match.seats[self.me].deck
        self.assertNotIn(uid, [c["uid"] for c in deck.discard_pile + deck.draw_pile + self.match.seats[self.me].hand])
        self.assertIn("on Player", self.match.log[-1]["text"])
        self.assertIn("leaves their deck", self.match.log[-1]["text"])

    def test_goblin_placement_refused(self):
        uid = give(self.match, self.me, "goblin-gap")
        for board_pid in (None, self.me, "p9"):
            with self.assertRaisesRegex(LobbyError, "opponent's board"):
                self.match.place(self.me, uid, 0, 0, 0, board_pid)
        self.match.seats[self.third].out = True
        with self.assertRaisesRegex(LobbyError, "opponent's board"):
            self.match.place(self.me, uid, 0, 0, 0, self.third)
        fill(self.match, self.other, [(0, 2)])
        with self.assertRaisesRegex(LobbyError, "doesn't fit"):
            self.match.place(self.me, uid, 0, 0, 0, self.other)  # (0, 0) and (0, 2)
        self.match.place(self.me, uid, 0, 0, 1, self.other)  # the gap may hold a tile
        normal = give(self.match, self.me, "dagger")
        with self.assertRaisesRegex(LobbyError, "goes on your own board"):
            self.match.place(self.me, normal, 0, 5, 5, self.other)

    def test_the_tile_spoils_not_the_face(self):
        seat = self.match.seats[self.me]
        # A goblin face on a blue tile does nothing; a bare goblin tile still spoils the line.
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        seat.board[0][3], seat.board[0][4] = ("blue", "goblin"), cell("C")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(seat.gold, 2)  # starting 1 + the coin
        self.assertNotIn("spoiled", self.match.log[-1]["text"])
        fill(self.match, self.me, row_cells(1, skip=(0,)))
        seat.board[1][3], seat.board[1][4] = ("goblin", None), cell("C")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 1, 0)
        self.assertEqual(seat.gold, 2)
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_goblin_line_has_no_effect(self):
        seat = self.match.seats[self.me]
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        seat.board[0][3], seat.board[0][4], seat.board[0][5] = cell("G"), cell("C"), cell("A")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(seat.gold, 1)  # unchanged (starting gold)
        self.assertEqual(self.match.seats[self.other].health, 10)
        self.assertEqual(rows(seat.board)[0], "." * 9)  # still cleared
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_goblins_do_not_spoil_grey_tiles(self):
        seat = self.match.seats[self.me]
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        # A goblin, two grey siege tiles, a grey coin, a normal coin and a normal (not grey) siege.
        for c, ch in zip(range(3, 9), "Geec" + "CE"):
            seat.board[0][c] = cell(ch)
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(seat.siege, 2)  # only the grey siege tiles
        self.assertEqual(seat.gold, 2)  # starting gold + the grey coin
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_grey_siege_card_counts_through_goblin_line(self):
        seat = self.match.seats[self.me]
        seat.board[0][4] = cell("G")
        self.match.place(self.me, give(self.match, self.me, "trebuchet"), 0, 0, 0)  # e at (0,0) (1,3) (3,1)
        for c in range(9):
            if seat.board[0][c] is None:
                seat.board[0][c] = cell("#")
        seat.board[0][8] = None
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 8)
        self.assertEqual(seat.siege, 1)

    def test_clean_crossing_line_still_counts_the_cell(self):
        seat = self.match.seats[self.me]
        # Row 0 holds a goblin; column 8 is clean. A Dagger at (0, 8) completes both: its attack
        # counts through column 8, while the attack at (0, 5) lies only in the spoiled row.
        fill(self.match, self.me, row_cells(0, skip=(8,)) + col_cells(8, skip=(0,)))
        seat.board[0][3], seat.board[0][5] = cell("G"), cell("A")
        self.match.place(self.me, give(self.match, self.me, "dagger"), 0, 0, 8)
        self.assertEqual(self.match.seats[self.other].health, 9)
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_goblin_completing_opponent_line_clears_without_effect(self):
        fill(self.match, self.other, row_cells(4, skip=(1, 3)))
        self.match.seats[self.other].board[4][6] = cell("C")
        self.match.place(self.me, give(self.match, self.me, "goblin-gap"), 0, 4, 1, self.other)
        self.assertEqual(rows(self.match.seats[self.other].board)[4], "." * 9)
        self.assertEqual(self.match.seats[self.other].gold, 2)  # starting gold only
        self.assertEqual(self.match.last_clear["pid"], self.other)


class SiegeTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def clear_row(self, letters):
        """Row 0 of my board: `letters`, then blanks; a patch at (0, 8) completes it."""
        cells = row_cells(0, skip=(8,))
        for (r, c), letter in zip(cells, letters + "#" * len(cells)):
            self.match.seats[self.me].board[r][c] = cell(letter)
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 8)

    def test_siege_card_placed_then_exiled(self):
        uid = give(self.match, self.me, "trebuchet")
        self.match.place(self.me, uid, 0, 0, 0)
        view = rows(self.match.seats[self.me].board)
        self.assertEqual((view[0][0], view[1][3], view[3][1]), ("e", "e", "e"))  # grey siege tiles
        seat = self.match.seats[self.me]
        self.assertNotIn(uid, [c["uid"] for c in seat.deck.discard_pile + seat.deck.draw_pile + seat.hand])

    def test_patched_exile_card_is_discarded_normally(self):
        uid = give(self.match, self.me, "catapult")
        self.match.patch(self.me, uid, 5, 5)
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me].deck.discard_pile])

    def test_three_siege_give_strength_and_progress_carries(self):
        seat = self.match.seats[self.me]
        self.clear_row("EE")
        self.assertEqual((seat.siege, seat.strength), (2, 0))
        self.assertIn("+2 siege.", self.match.log[-1]["text"])
        self.clear_row("EE")  # 4 in all: 1 strength, 1 towards the next
        self.assertEqual((seat.siege, seat.strength), (1, 1))
        self.assertIn("+1 strength", self.match.log[-1]["text"])

    def test_strength_adds_to_total_damage(self):
        seat, defender = self.match.seats[self.me], self.match.seats[self.other]
        seat.strength = 1
        defender.shield = 1
        self.clear_row("AA")  # 2 attacks + 1 strength = 3, 1 blocked
        self.assertEqual((defender.shield, defender.health), (0, 8))
        self.assertIn("3 damage", self.match.log[-1]["text"])

    def test_strength_needs_an_attack(self):
        self.match.seats[self.me].strength = 2
        self.clear_row("C")
        self.assertEqual(self.match.seats[self.other].health, 10)

    def test_new_strength_applies_from_next_clear(self):
        self.clear_row("EEEA")
        self.assertEqual(self.match.seats[self.me].strength, 1)
        self.assertEqual(self.match.seats[self.other].health, 9)  # 1 damage: strength counts from the next clear


class PureEffectTests(unittest.TestCase):
    """effects.py on its own: a board and a seat, no Match."""

    def setUp(self):
        self.seat = new_match().seats["p1"]

    def test_clear_lines_nothing_full(self):
        self.seat.board[0][0] = cell("C")
        self.assertIsNone(effects.clear_lines(self.seat.board))
        self.assertEqual(self.seat.board[0][0], cell("C"))

    def test_clear_lines_counts_and_spoils(self):
        grid = self.seat.board
        for r, c in row_cells(0):
            grid[r][c] = cell("#")
        for r, c in col_cells(8):
            grid[r][c] = cell("#")
        grid[0][2], grid[0][4], grid[5][8], grid[0][8] = cell("G"), cell("C"), cell("A"), cell("S")
        cleared = effects.clear_lines(grid)
        self.assertEqual((cleared.rows, cleared.cols, cleared.spoiled), ([0], [8], 1))
        self.assertEqual(cleared.counts, {"attack": 1, "shield": 1})  # the coin is only in the spoiled row
        self.assertEqual(len(cleared.removed), 17)
        self.assertEqual(rows(grid), ["." * 9] * 9)

    def test_apply_symbols_and_damage(self):
        self.seat.strength = 2
        clear = effects.apply_symbols(self.seat, {"coin": 2, "attack": 1, "siege": 3})
        self.assertEqual(self.seat.strength, 3)
        self.assertEqual(clear.damage, 3)  # 1 attack + the strength from before the clear
        self.assertIn("+2 gold", clear.gains)
        self.assertEqual(effects.apply_symbols(self.seat, {"coin": 1}).damage, 0)  # no attack, no damage
        defender = new_match().seats["p2"]
        defender.shield, defender.health = 1, 2
        self.assertEqual(effects.deal_damage(defender, 5), 1)
        self.assertEqual((defender.shield, defender.health), (0, 0))  # never below 0


if __name__ == "__main__":
    unittest.main()

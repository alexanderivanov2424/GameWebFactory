"""Block Blast: tests. Run: python3 -I tools/run_tests.py block-blast

- Rules tests drive logic.Match directly (fast, no lobby): set up a position, act, check.
- Lobby tests go through the real lobby with gamekit.sim.Sim, the way browsers do: settings,
  turn checks, what each player and spectator receives, leaving mid-game.
"""

import importlib
import json
import random
import unittest

from gamekit import LobbyError
from gamekit.sim import Sim

GAME = "block-blast"
Match = importlib.import_module(f"games.{GAME}.logic.match").Match  # the id contains "-"
board = importlib.import_module(f"games.{GAME}.logic.board")
symbols = importlib.import_module(f"games.{GAME}.logic.symbols")
bank_module = importlib.import_module(f"games.{GAME}.logic.bank")

SETTINGS = {"health": 10}


def new_match(players=2, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    return Match(names, {**SETTINGS, **settings}, rng=random.Random(1))


def give(match, pid, card_id):
    """Put a fresh instance of card_id into pid's hand; returns its uid."""
    card = match.seats[pid]["deck"].make(card_id)
    match.seats[pid]["hand"].append(card)
    return card["uid"]


# Board cells written as one letter, for short tests: "#" blue blank, "C"/"A"/"S"/"R"/"E" a symbol
# on a blue tile, lowercase = that symbol on a grey tile ("+" grey blank), "G" a goblin tile.
SYMBOL_OF = {code: name for name, code in symbols.SYMBOLS.items()}


def cell(letter):
    if letter == "#":
        return ("blue", None)
    if letter == "+":
        return ("grey", None)
    if letter == "G":
        return ("goblin", None)
    if letter.islower():
        return ("grey", SYMBOL_OF[letter.upper()])
    return ("blue", SYMBOL_OF[letter])


def letter_of(c):
    if c is None:
        return "."
    tile, symbol = c
    code = symbols.SYMBOLS[symbol] if symbol else None
    if tile == "goblin":
        return "G"
    if tile == "grey":
        return code.lower() if code else "+"
    return code or "#"


def rows(grid):
    """A board as strings of the letters above ("." empty)."""
    return ["".join(letter_of(c) for c in row) for row in grid]


def fill(match, pid, cells, letter="#"):
    for r, c in cells:
        match.seats[pid]["board"][r][c] = cell(letter)


def row_cells(r, skip=()):
    return [(r, c) for c in range(board.SIZE) if c not in skip]


def col_cells(c, skip=()):
    return [(r, c) for r in range(board.SIZE) if r not in skip]


class SetupTests(unittest.TestCase):
    def test_starting_hands_and_bank(self):
        match = new_match(players=3)
        for place, pid in enumerate(match.order):
            seat = match.seats[pid]
            self.assertEqual(len(seat["hand"]), 3)
            self.assertEqual(len(seat["deck"]), 3)
            self.assertEqual(seat["health"], 10)
            self.assertEqual(seat["gold"], place + 1)  # 1 for the first player, 2, 3
        self.assertEqual(len(match.bank.slots), 5)
        self.assertTrue(all(match.bank.slots))
        self.assertEqual(len(match.bank.deck), 49 - 5)

    def test_initial_targets_are_next_in_order(self):
        match = new_match(players=3)
        a, b, c = match.order
        self.assertEqual(match.seats[a]["target"], b)
        self.assertEqual(match.seats[c]["target"], a)
        self.assertEqual(match.turn(), a)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_place_rotated_shape(self):
        uid = give(self.match, self.me, "hook")  # "#." "#." "A#"
        self.match.place(self.me, uid, 1, 0, 0)  # one turn clockwise: "A##" "#.."
        view = rows(self.match.seats[self.me]["board"])
        self.assertEqual(view[0][:3], "A##")
        self.assertEqual(view[1][:3], "#..")
        self.assertNotIn(uid, [c["uid"] for c in self.match.seats[self.me]["hand"]])
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me]["deck"].discard_pile])

    def test_off_board_overlap_and_unknown_card_refused(self):
        uid = give(self.match, self.me, "bar-4")
        with self.assertRaisesRegex(LobbyError, "doesn't fit"):
            self.match.place(self.me, uid, 0, 0, 6)  # columns 6..9
        fill(self.match, self.me, [(4, 4)])
        with self.assertRaisesRegex(LobbyError, "doesn't fit"):
            self.match.place(self.me, uid, 1, 2, 4)  # vertical over (4, 4)
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            self.match.place(self.me, 999, 0, 0, 0)
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me]["hand"]])  # unchanged

    def test_not_your_turn(self):
        uid = give(self.match, self.other, "dagger")
        with self.assertRaisesRegex(LobbyError, "not your turn"):
            self.match.place(self.other, uid, 0, 0, 0)

    def test_patch_places_blank_tile(self):
        uid = give(self.match, self.me, "great-cross")
        self.match.patch(self.me, uid, 8, 8)
        self.assertEqual(self.match.seats[self.me]["board"][8][8], ("blue", None))
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me]["deck"].discard_pile])

    def test_multiple_cards_per_turn(self):
        hand = [c["uid"] for c in self.match.seats[self.me]["hand"]]
        for i, uid in enumerate(hand):
            self.match.patch(self.me, uid, i, 0)
        self.assertEqual(self.match.seats[self.me]["hand"], [])
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
        gold = seat["gold"]
        self.match.place(self.me, uid, 0, 3, 0)
        self.assertEqual(seat["gold"], gold + 2)
        self.assertEqual(self.match.seats[self.other]["health"], 8)
        self.assertEqual(rows(seat["board"])[3], "." * 9)
        self.assertEqual(seat["board"][4][4], ("blue", None))
        self.assertEqual(len(self.match.last_clear["cells"]), 9)

    def test_row_and_column_share_a_cell_once(self):
        # Row 0 and column 0 both complete when (0, 0) is filled; it holds an attack.
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        fill(self.match, self.me, col_cells(0, skip=(0,)))
        uid = give(self.match, self.me, "dagger")
        self.match.place(self.me, uid, 0, 0, 0)
        self.assertEqual(self.match.seats[self.other]["health"], 9)  # 1 attack, not 2
        self.assertEqual(len(self.match.last_clear["cells"]), 17)
        self.assertTrue(all(c is None for row in self.match.seats[self.me]["board"] for c in row))

    def test_two_rows_at_once(self):
        fill(self.match, self.me, row_cells(0, skip=(0,)) + row_cells(1, skip=(0,)))
        uid = give(self.match, self.me, "bar-2")
        self.match.place(self.me, uid, 1, 0, 0)  # vertical bar in column 0
        self.assertIn("2 rows", self.match.log[-1]["text"])

    def test_knock_out_ends_two_player_game(self):
        self.match.seats[self.other]["health"] = 1
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        uid = give(self.match, self.me, "dagger")
        self.match.place(self.me, uid, 0, 0, 0)
        self.assertEqual(self.match.seats[self.other]["health"], 0)
        self.assertEqual(self.match.result["winner"], self.me)
        self.assertIsNone(self.match.turn())


class ShieldTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def clear_row(self, pid, letters):
        """Row 0 of pid's board: `letters`, then blanks, then a patch at (0, 8) completes it."""
        cells = row_cells(0, skip=(8,))
        for (r, c), letter in zip(cells, letters + "#" * len(cells)):
            self.match.seats[pid]["board"][r][c] = cell(letter)
        self.match.patch(pid, give(self.match, pid, "bar-2"), 0, 8)

    def test_clearing_shields_adds_shield(self):
        self.clear_row(self.me, "SS")
        self.assertEqual(self.match.seats[self.me]["shield"], 2)
        self.assertIn("+2 shield", self.match.log[-1]["text"])

    def test_shield_absorbs_damage_and_is_used_up(self):
        defender = self.match.seats[self.other]
        defender["shield"] = 2
        self.clear_row(self.me, "AAA")
        self.assertEqual(defender["shield"], 0)
        self.assertEqual(defender["health"], 9)  # 3 attacks - 2 blocked
        self.assertIn("2 blocked", self.match.log[-1]["text"])

    def test_shield_bigger_than_attack(self):
        defender = self.match.seats[self.other]
        defender["shield"] = 3
        self.clear_row(self.me, "A")
        self.assertEqual((defender["shield"], defender["health"]), (2, 10))

    def test_shield_decays_at_start_of_own_turn_only(self):
        mine, theirs = self.match.seats[self.me], self.match.seats[self.other]
        mine["shield"], theirs["shield"] = 3, 3
        self.match.end_turn(self.me)  # other's turn starts
        self.assertEqual((mine["shield"], theirs["shield"]), (3, 2))
        self.match.end_turn(self.other)  # my turn starts
        self.assertEqual((mine["shield"], theirs["shield"]), (2, 2))
        mine["shield"] = 0
        self.match.end_turn(self.me)
        self.match.end_turn(self.other)
        self.assertEqual(mine["shield"], 0)  # never below 0

    def test_shield_does_not_stop_knock_out(self):
        defender = self.match.seats[self.other]
        defender["shield"], defender["health"] = 1, 1
        self.clear_row(self.me, "AA")
        self.assertEqual(defender["health"], 0)
        self.assertEqual(self.match.result["winner"], self.me)


class ChapelTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_clearing_chapel_gives_removal(self):
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        self.match.seats[self.me]["board"][0][3] = cell("R")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(self.match.seats[self.me]["chapels"], 1)
        self.assertIn("+1 card removal", self.match.log[-1]["text"])

    def test_remove_card_leaves_deck_for_good(self):
        seat = self.match.seats[self.other]  # off-turn: allowed any time
        seat["chapels"] = 1
        card = seat["hand"][0]
        total = len(seat["hand"]) + len(seat["deck"]) + len(seat["deck"].discard_pile)
        self.match.remove_card(self.other, card["uid"])
        self.assertEqual(seat["chapels"], 0)
        self.assertNotIn(card, seat["hand"])
        self.assertNotIn(card, seat["deck"].discard_pile)
        self.assertNotIn(card, seat["deck"].draw_pile)
        self.assertEqual(len(seat["hand"]) + len(seat["deck"]) + len(seat["deck"].discard_pile), total - 1)
        self.assertIn("removed", self.match.log[-1]["text"])

    def test_remove_refused(self):
        seat = self.match.seats[self.me]
        with self.assertRaisesRegex(LobbyError, "no card removals"):
            self.match.remove_card(self.me, seat["hand"][0]["uid"])
        seat["chapels"] = 1
        with self.assertRaisesRegex(LobbyError, "isn't in your hand"):
            self.match.remove_card(self.me, 999)
        self.assertEqual(seat["chapels"], 1)  # not spent on a refusal
        seat["out"] = True
        with self.assertRaisesRegex(LobbyError, "out of the game"):
            self.match.remove_card(self.me, seat["hand"][0]["uid"])


class GoblinTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match(players=3)
        self.me, self.other, self.third = self.match.order

    def test_goblin_goes_on_opponent_board_and_leaves_my_deck(self):
        uid = give(self.match, self.me, "goblin-siege")  # 4 corners of a 3x3
        self.match.place(self.me, uid, 0, 2, 2, self.other)
        board_rows = rows(self.match.seats[self.other]["board"])
        self.assertEqual((board_rows[2][2], board_rows[2][4], board_rows[4][2], board_rows[4][4]), ("G",) * 4)
        self.assertEqual(rows(self.match.seats[self.me]["board"]), ["." * 9] * 9)
        deck = self.match.seats[self.me]["deck"]
        self.assertNotIn(uid, [c["uid"] for c in deck.discard_pile + deck.draw_pile + self.match.seats[self.me]["hand"]])
        self.assertIn("on Player", self.match.log[-1]["text"])
        self.assertIn("leaves their deck", self.match.log[-1]["text"])

    def test_goblin_placement_refused(self):
        uid = give(self.match, self.me, "goblin-gap")
        for board_pid in (None, self.me, "p9"):
            with self.assertRaisesRegex(LobbyError, "opponent's board"):
                self.match.place(self.me, uid, 0, 0, 0, board_pid)
        self.match.seats[self.third]["out"] = True
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
        seat["board"][0][3], seat["board"][0][4] = ("blue", "goblin"), cell("C")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(seat["gold"], 2)  # starting 1 + the coin
        self.assertNotIn("spoiled", self.match.log[-1]["text"])
        fill(self.match, self.me, row_cells(1, skip=(0,)))
        seat["board"][1][3], seat["board"][1][4] = ("goblin", None), cell("C")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 1, 0)
        self.assertEqual(seat["gold"], 2)
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_goblin_line_has_no_effect(self):
        seat = self.match.seats[self.me]
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        seat["board"][0][3], seat["board"][0][4], seat["board"][0][5] = cell("G"), cell("C"), cell("A")
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(seat["gold"], 1)  # unchanged (starting gold)
        self.assertEqual(self.match.seats[self.other]["health"], 10)
        self.assertEqual(rows(seat["board"])[0], "." * 9)  # still cleared
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_goblins_do_not_spoil_grey_tiles(self):
        seat = self.match.seats[self.me]
        fill(self.match, self.me, row_cells(0, skip=(0,)))
        # A goblin, two grey siege tiles, a grey coin, a normal coin and a normal (not grey) siege.
        for c, ch in zip(range(3, 9), "Geec" + "CE"):
            seat["board"][0][c] = cell(ch)
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 0)
        self.assertEqual(seat["siege"], 2)  # only the grey siege tiles
        self.assertEqual(seat["gold"], 2)  # starting gold + the grey coin
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_grey_siege_card_counts_through_goblin_line(self):
        seat = self.match.seats[self.me]
        seat["board"][0][4] = cell("G")
        self.match.place(self.me, give(self.match, self.me, "trebuchet"), 0, 0, 0)  # e at (0,0) (1,3) (3,1)
        for c in range(9):
            if seat["board"][0][c] is None:
                seat["board"][0][c] = cell("#")
        seat["board"][0][8] = None
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 8)
        self.assertEqual(seat["siege"], 1)

    def test_clean_crossing_line_still_counts_the_cell(self):
        seat = self.match.seats[self.me]
        # Row 0 holds a goblin; column 8 is clean. A Dagger at (0, 8) completes both: its attack
        # counts through column 8, while the attack at (0, 5) lies only in the spoiled row.
        fill(self.match, self.me, row_cells(0, skip=(8,)) + col_cells(8, skip=(0,)))
        seat["board"][0][3], seat["board"][0][5] = cell("G"), cell("A")
        self.match.place(self.me, give(self.match, self.me, "dagger"), 0, 0, 8)
        self.assertEqual(self.match.seats[self.other]["health"], 9)
        self.assertIn("Goblins spoiled 1 line", self.match.log[-1]["text"])

    def test_goblin_completing_opponent_line_clears_without_effect(self):
        fill(self.match, self.other, row_cells(4, skip=(1, 3)))
        self.match.seats[self.other]["board"][4][6] = cell("C")
        self.match.place(self.me, give(self.match, self.me, "goblin-gap"), 0, 4, 1, self.other)
        self.assertEqual(rows(self.match.seats[self.other]["board"])[4], "." * 9)
        self.assertEqual(self.match.seats[self.other]["gold"], 2)  # starting gold only
        self.assertEqual(self.match.last_clear["pid"], self.other)


class SiegeTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def clear_row(self, letters):
        """Row 0 of my board: `letters`, then blanks; a patch at (0, 8) completes it."""
        cells = row_cells(0, skip=(8,))
        for (r, c), letter in zip(cells, letters + "#" * len(cells)):
            self.match.seats[self.me]["board"][r][c] = cell(letter)
        self.match.patch(self.me, give(self.match, self.me, "bar-2"), 0, 8)

    def test_siege_card_placed_then_exiled(self):
        uid = give(self.match, self.me, "trebuchet")
        self.match.place(self.me, uid, 0, 0, 0)
        view = rows(self.match.seats[self.me]["board"])
        self.assertEqual((view[0][0], view[1][3], view[3][1]), ("e", "e", "e"))  # grey siege tiles
        seat = self.match.seats[self.me]
        self.assertNotIn(uid, [c["uid"] for c in seat["deck"].discard_pile + seat["deck"].draw_pile + seat["hand"]])

    def test_patched_exile_card_is_discarded_normally(self):
        uid = give(self.match, self.me, "catapult")
        self.match.patch(self.me, uid, 5, 5)
        self.assertIn(uid, [c["uid"] for c in self.match.seats[self.me]["deck"].discard_pile])

    def test_three_siege_give_strength_and_progress_carries(self):
        seat = self.match.seats[self.me]
        self.clear_row("EE")
        self.assertEqual((seat["siege"], seat["strength"]), (2, 0))
        self.assertIn("+2 siege.", self.match.log[-1]["text"])
        self.clear_row("EE")  # 4 in all: 1 strength, 1 towards the next
        self.assertEqual((seat["siege"], seat["strength"]), (1, 1))
        self.assertIn("+1 strength", self.match.log[-1]["text"])

    def test_strength_adds_to_total_damage(self):
        seat, defender = self.match.seats[self.me], self.match.seats[self.other]
        seat["strength"] = 1
        defender["shield"] = 1
        self.clear_row("AA")  # 2 attacks + 1 strength = 3, 1 blocked
        self.assertEqual((defender["shield"], defender["health"]), (0, 8))
        self.assertIn("3 damage", self.match.log[-1]["text"])

    def test_strength_needs_an_attack(self):
        self.match.seats[self.me]["strength"] = 2
        self.clear_row("C")
        self.assertEqual(self.match.seats[self.other]["health"], 10)

    def test_new_strength_applies_from_next_clear(self):
        self.clear_row("EEEA")
        self.assertEqual(self.match.seats[self.me]["strength"], 1)
        self.assertEqual(self.match.seats[self.other]["health"], 9)  # 1 damage: strength counts from the next clear


class AimTests(unittest.TestCase):
    def test_aim_and_reaim_after_knock_out(self):
        match = new_match(players=3)
        a, b, c = match.order
        match.aim(a, c)
        self.assertEqual(match.seats[a]["target"], c)
        match.aim(b, a)  # off-turn aiming is allowed
        with self.assertRaises(LobbyError):
            match.aim(a, a)
        with self.assertRaises(LobbyError):
            match.aim(a, "p9")
        # One attack on a cleared row: c drops to 1.
        match.seats[c]["health"] = 2
        fill(match, a, row_cells(0, skip=(0,)))
        match.seats[a]["board"][0][1] = cell("A")
        match.place(a, give(match, a, "bar-2"), 1, 0, 0)  # vertical: completes row 0 only
        self.assertEqual(match.seats[c]["health"], 1)
        # A second one knocks c out; a re-aims at the next player still in (b).
        fill(match, a, row_cells(2, skip=(0,)), "A")
        match.patch(a, give(match, a, "dagger"), 2, 0)
        self.assertTrue(match.seats[c]["out"])
        self.assertEqual(match.seats[a]["target"], b)
        self.assertNotIn(c, match.queue)
        self.assertIsNone(match.result)
        with self.assertRaisesRegex(LobbyError, "still in"):
            match.aim(b, c)
        with self.assertRaisesRegex(LobbyError, "out of the game"):
            match.aim(c, a)


class BankTests(unittest.TestCase):
    def setUp(self):
        self.match = new_match()
        self.me, self.other = self.match.order

    def test_prices_by_slot_and_empty_until_end_of_turn(self):
        bank = self.match.bank
        seat = self.match.seats[self.me]
        seat["gold"] = 2
        with self.assertRaisesRegex(LobbyError, "costs 3 gold"):
            self.match.buy(self.me, 2)
        third = bank.slots[2]
        seat["gold"] = 5
        self.match.buy(self.me, 2)  # 3 gold
        self.assertEqual(seat["gold"], 2)
        self.assertIsNone(bank.slots[2])
        self.assertEqual([c["card"] for c in seat["deck"].discard_pile], [third["card"]])
        rest = [bank.slots[0], bank.slots[1], bank.slots[3], bank.slots[4]]
        left = len(bank.deck)
        self.match.end_turn(self.me)
        self.assertEqual(bank.slots[:4], rest)  # shifted towards slot 0
        self.assertTrue(all(bank.slots))
        self.assertEqual(len(bank.deck), left - 1)

    def test_one_buy_per_turn(self):
        seat = self.match.seats[self.me]
        seat["gold"] = 15
        self.match.buy(self.me, 0)
        self.assertEqual(self.match.public()["buysLeft"], 0)
        with self.assertRaisesRegex(LobbyError, "only buy 1 card a turn"):
            self.match.buy(self.me, 1)
        with self.assertRaisesRegex(LobbyError, "only buy 1"):
            self.match.buy(self.me, 0)  # the limit is checked before the empty slot
        self.assertEqual(seat["gold"], 14)
        self.match.end_turn(self.me)
        self.assertEqual(self.match.public()["buysLeft"], 1)  # the next player's buy
        self.match.seats[self.other]["gold"] = 5
        self.match.buy(self.other, 0)
        self.match.end_turn(self.other)
        self.match.buy(self.me, 0)  # a new turn, a new buy
        self.assertEqual(seat["gold"], 13)

    def test_bonus_deck_runs_out(self):
        bank = bank_module.Bank(["dagger"] * 7, random.Random(1))  # 5 dealt, 2 left
        bank.take(0)
        bank.take(1)
        bank.refill()
        self.assertEqual(sum(1 for s in bank.slots if s), 5)
        bank.take(0)
        bank.take(4)
        bank.refill()
        self.assertEqual(sum(1 for s in bank.slots if s), 3)
        self.assertEqual(bank.slots[3:], [None, None])

    def test_bought_cards_have_own_uids(self):
        self.match.buy(self.me, 0)
        uids = [c["uid"] for c in self.match.seats[self.me]["hand"]]
        uids += [c["uid"] for c in self.match.seats[self.me]["deck"].draw_pile]
        uids += [c["uid"] for c in self.match.seats[self.me]["deck"].discard_pile]
        self.assertEqual(len(uids), len(set(uids)))


class TurnTests(unittest.TestCase):
    def test_end_turn_draws_to_three_and_reshuffles(self):
        match = new_match()
        me, other = match.order
        seat = match.seats[me]
        # Play the whole hand as patches on distinct cells.
        for i, uid in enumerate([c["uid"] for c in seat["hand"]]):
            match.patch(me, uid, 5, i)
        match.end_turn(me)
        self.assertEqual(len(seat["hand"]), 3)
        self.assertEqual(len(seat["deck"]), 0)
        self.assertEqual(match.turn(), other)
        match.end_turn(other)
        for i, uid in enumerate([c["uid"] for c in seat["hand"]]):
            match.patch(me, uid, 6, i)
        match.end_turn(me)  # draw pile empty: the 6 discards are reshuffled
        self.assertEqual(len(seat["hand"]), 3)
        self.assertEqual(len(seat["deck"]), 3)
        self.assertEqual(len(seat["deck"].discard_pile), 0)

    def test_unplayed_cards_stay(self):
        match = new_match()
        me, _ = match.order
        hand = list(match.seats[me]["hand"])
        match.end_turn(me)
        self.assertEqual(match.seats[me]["hand"], hand)

    def test_leaving_on_own_turn_passes_turn_and_refills_bank(self):
        match = new_match(players=3)
        a, b, c = match.order
        match.buy(a, 0)
        match.remove(a)
        self.assertEqual(match.turn(), b)
        self.assertTrue(all(match.bank.slots))
        self.assertEqual(match.seats[c]["target"], b)
        self.assertIsNone(match.result)
        match.remove(c)
        self.assertEqual(match.result["winner"], b)

    def test_leaving_off_turn(self):
        match = new_match(players=3)
        a, b, c = match.order
        match.remove(b)
        self.assertEqual(match.turn(), a)
        self.assertEqual(match.seats[a]["target"], c)
        match.end_turn(a)
        self.assertEqual(match.turn(), c)


class SettingsTests(unittest.TestCase):
    def test_clamped_and_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"health": "x"}}))
        sim.lobby(0, {"type": "settings", "settings": {"health": 500}})
        self.assertEqual(sim.state(0)["settings"], {"health": 50})


class LobbyTests(unittest.TestCase):
    def new_game(self, players=2, **settings):
        sim = Sim(GAME, players=players, settings=settings or None)
        order = [sim.index_of(pid) for pid in sim.game.match.queue.order()]
        return sim, order

    def test_settings_apply(self):
        sim, order = self.new_game(health=3)
        seats = sim.state(0)["game"]["seats"]
        self.assertEqual([seats[sim.pid(i)]["gold"] for i in order], [1, 2])
        self.assertEqual(seats[sim.pid(0)]["health"], 3)

    def test_not_your_turn_and_bad_messages(self):
        sim, (first, second) = self.new_game()
        uid = sim.state(second)["private"]["hand"][0]["uid"]
        sim.fails(second, {"action": "place", "uid": uid, "rotation": 0, "row": 0, "col": 0}, "not your turn")
        uid = sim.state(first)["private"]["hand"][0]["uid"]
        sim.fails(first, {"action": "place", "uid": uid, "rotation": True, "row": 0, "col": 0}, "whole number")
        sim.fails(first, {"action": "place", "uid": uid, "rotation": 4, "row": 0, "col": 0}, "Rotation")
        sim.fails(first, {"action": "place", "uid": uid, "rotation": 0, "row": 9, "col": 0}, "Row")
        sim.fails(first, {"action": "buy", "slot": 5}, "Slot")
        sim.fails(first, {"action": "fly"}, "")
        sim.ok(first, {"action": "place", "uid": uid, "rotation": 0, "row": 0, "col": 0})
        sim.ok(second, {"action": "aim", "player": sim.pid(first)})
        sim.game.match.seats[sim.pid(second)]["chapels"] = 1
        uid2 = sim.state(second)["private"]["hand"][0]["uid"]
        sim.ok(second, {"action": "remove", "uid": uid2})  # off-turn removal is allowed
        self.assertEqual(len(sim.state(second)["private"]["hand"]), 2)
        self.assertEqual(sim.state(first)["game"]["seats"][sim.pid(second)]["chapels"], 0)
        sim.ok(first, {"action": "buy", "slot": 0})
        sim.ok(first, {"action": "end_turn"})
        self.assertEqual(sim.state(first)["game"]["turn"], sim.pid(second))

    def test_hidden_info_not_leaked(self):
        sim, (first, second) = self.new_game()
        watcher = sim.spectator()
        match = sim.game.match
        for i in (first, second):  # each player gets exactly their own hand
            self.assertEqual(sim.state(i)["private"]["hand"], match.seats[sim.pid(i)]["hand"])
        self.assertIsNone(sim.state(watcher)["private"])
        public = sim.state(watcher)["game"]
        for pid in (sim.pid(first), sim.pid(second)):
            self.assertEqual(public["seats"][pid]["hand"], 3)  # a count, not the cards
        self.assertNotIn("uid", json.dumps(public["seats"]))

    def test_game_end(self):
        sim, (first, second) = self.new_game(health=1)
        match = sim.game.match
        fill(match, sim.pid(first), row_cells(0, skip=(0,)), "A")
        uid = sim.state(first)["private"]["hand"][0]["uid"]
        sim.ok(first, {"action": "patch", "uid": uid, "row": 0, "col": 0})
        state = sim.state(second)
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["result"]["winner"], sim.pid(first))

    def test_player_leaves_mid_game(self):
        sim, (first, second) = self.new_game()
        sim.leave(first)
        self.assertEqual(sim.state(second)["phase"], "finished")
        self.assertEqual(sim.state(second)["result"]["winner"], sim.pid(second))

    def test_three_players_one_leaves(self):
        sim, order = self.new_game(players=3)
        sim.leave(order[0])
        state = sim.state(order[1])
        self.assertEqual(state["phase"], "playing")
        self.assertEqual(state["game"]["turn"], sim.pid(order[1]))
        self.assertTrue(state["game"]["seats"][sim.pid(order[0])]["out"])


if __name__ == "__main__":
    unittest.main()

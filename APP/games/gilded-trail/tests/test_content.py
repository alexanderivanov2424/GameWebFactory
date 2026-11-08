"""Gilded Trail: content tests (cards, maps, board generation).

Checks that the files load and every map builds; not their balance.
Run: python3 -I tools/run_tests.py gilded-trail
"""

import importlib
import unittest

helpers = importlib.import_module("games.gilded-trail.tests.helpers")
board_mod = importlib.import_module("games.gilded-trail.logic.board")
Board = board_mod.Board
CARDS, MAPS = helpers.CARDS, helpers.MAPS


def reachable(board):
    """Hexes connected to the goals through passable spaces (starts included, not crossed)."""
    seen, stack = set(board.goals), list(board.goals)
    while stack:
        for n in board_mod.neighbors(stack.pop()):
            h = board.hexes.get(n)
            if h is None or n in seen:
                continue
            if h["t"] == "start":
                seen.add(n)
            elif board_mod.passable(h):
                seen.add(n)
                stack.append(n)
    return seen


class CardTests(unittest.TestCase):
    def test_cards_load(self):
        self.assertGreaterEqual(len(CARDS), 10)
        for cid in ("porter", "trader", "boatman"):
            self.assertIn(cid, CARDS)

    def test_card_shapes(self):
        for cid, c in CARDS.items():
            self.assertIn(c["kind"], ("machete", "paddle", "coin", "joker", "action"), cid)
            if c["kind"] == "action":
                self.assertTrue(c["effect"], cid)
            else:
                self.assertGreaterEqual(c["value"], 1, cid)

    def test_start_cards_are_not_for_sale(self):
        for cid in ("porter", "trader", "boatman"):
            self.assertNotIn("cost", CARDS[cid])

    def test_start_market_cards_exist_and_cost(self):
        market = helpers.new_match().market
        self.assertEqual(len(market.slots), 6)
        for cid in market.slots:
            self.assertIn("cost", CARDS[cid])


class MapTests(unittest.TestCase):
    def test_maps_load(self):
        self.assertGreaterEqual(len(MAPS), 1)

    def test_every_preset_builds_with_a_route(self):
        for mid, preset in MAPS.items():
            board = Board(preset)
            self.assertEqual(board.tiles, len(preset["dirs"]) + 1, mid)
            self.assertEqual(len(board.blockades), board.tiles - 1, mid)
            self.assertEqual(len(board.starts), 4, mid)
            self.assertEqual(len(board.goals), 3, mid)
            seen = reachable(board)
            for start in board.starts:
                self.assertIn(start, seen, f"{mid}: {start} can't reach the goal")

    def test_presets_are_the_same_every_time(self):
        for mid, preset in MAPS.items():
            self.assertEqual(Board(preset).hexes, Board(preset).hexes, mid)

    def test_random_boards_are_deterministic_per_seed(self):
        a, b = Board(None, 42, 5), Board(None, 42, 5)
        self.assertEqual(a.hexes, b.hexes)
        self.assertEqual(a.blockades, b.blockades)
        self.assertNotEqual(a.hexes, Board(None, 43, 5).hexes)

    def test_random_boards_build_for_several_seeds_and_lengths(self):
        for tiles in (3, 6, 9):
            for seed in (1, 2, 3, 77):
                board = Board(None, seed, tiles)
                self.assertEqual(board.tiles, tiles)
                self.assertEqual(len(board.blockades), tiles - 1)
                seen = reachable(board)
                self.assertTrue(all(s in seen for s in board.starts), (tiles, seed))

    def test_goals_are_marked_and_blockades_have_edges(self):
        board = Board(MAPS["serpent"])
        for g in board.goals:
            self.assertTrue(board.hexes[g].get("goal"))
        for b in board.blockades:
            self.assertTrue(b["edges"])
            self.assertIn(b["t"], ("machete", "paddle", "coin", "rubble"))

    def test_make_board_uses_seed_setting(self):
        make = importlib.import_module("games.gilded-trail.logic.match").make_board
        board, seed = make({"map": "random", "seed": 123, "tiles": 4})
        self.assertEqual(seed, 123)
        self.assertEqual(board.hexes, Board(None, 123, 4).hexes)
        self.assertEqual(make({"map": "serpent"})[1], None)

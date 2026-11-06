"""Color Tic-Tac-Toe: colors, settings, placing, winning, draws and leaving."""

import unittest

from gamekit.sim import Sim


def new_game(players=2, **settings):
    sim = Sim("tictactoe", players=players, settings=settings or None)
    order = sim.game.queue.order()  # turn order is random: index players by it
    return sim, [sim.index_of(pid) for pid in order]


class LobbyTests(unittest.TestCase):
    def test_colors_unique_and_valid(self):
        sim = Sim("tictactoe", players=2, start=False)
        taken = sim.member(0).options["color"]
        self.assertNotEqual(sim.member(1).options["color"], taken)
        self.assertIn("already has that color", sim.lobby(1, {"type": "options", "options": {"color": taken}}))
        self.assertIn("Pick a color", sim.lobby(1, {"type": "options", "options": {"color": "red"}}))
        self.assertIsNone(sim.lobby(1, {"type": "options", "options": {"color": "#ABCDEF"}}))
        self.assertEqual(sim.member(1).options["color"], "#abcdef")

    def test_win_length_follows_board_size(self):
        sim = Sim("tictactoe", start=False)
        sim.lobby(0, {"type": "settings", "settings": {"boardSize": 4, "winLength": 9}})
        self.assertEqual(sim.game.settings, {"boardSize": 4, "winLength": 4})
        sim.lobby(0, {"type": "settings", "settings": {"boardSize": 99}})
        self.assertEqual(sim.game.settings["boardSize"], 10)


class PlayTests(unittest.TestCase):
    def test_turns_and_invalid_moves(self):
        sim, (a, b) = new_game()
        sim.fails(b, {"action": "place", "row": 0, "col": 0}, "not your turn")
        sim.fails(a, {"action": "place", "row": 3, "col": 0}, "not a square")
        sim.fails(a, {"action": "place", "row": True, "col": 0}, "not a square")
        sim.ok(a, {"action": "place", "row": 0, "col": 0})
        sim.fails(b, {"action": "place", "row": 0, "col": 0}, "taken")
        self.assertEqual(sim.state(b)["game"]["lastMove"], [0, 0])

    def test_row_wins(self):
        sim, (a, b) = new_game()
        for col in range(2):
            sim.ok(a, {"action": "place", "row": 0, "col": col})
            sim.ok(b, {"action": "place", "row": 1, "col": col})
        sim.ok(a, {"action": "place", "row": 0, "col": 2})
        result = sim.state(b)["result"]
        self.assertEqual(sim.game.phase, "finished")
        self.assertEqual(result["winner"], sim.pid(a))
        self.assertEqual(result["line"], [[0, 0], [0, 1], [0, 2]])

    def test_full_board_is_a_draw(self):
        sim, (a, b) = new_game()
        # a b a / a b b / b a a  -> no three in a row
        moves = [(a, 0, 0), (b, 0, 1), (a, 0, 2), (b, 1, 1), (a, 1, 0), (b, 1, 2), (a, 2, 1), (b, 2, 0), (a, 2, 2)]
        for player, row, col in moves:
            sim.ok(player, {"action": "place", "row": row, "col": col})
        self.assertEqual(sim.state(a)["result"]["winner"], None)
        self.assertEqual(sim.state(a)["result"]["reason"], "The board is full.")

    def test_last_player_left_wins(self):
        sim, (a, b) = new_game()
        sim.leave(b)
        self.assertEqual(sim.state(a)["result"]["winner"], sim.pid(a))

    def test_leaving_on_your_turn_passes_it_on(self):
        sim, (a, b, c) = new_game(players=3)
        sim.leave(a)
        self.assertEqual(sim.game.phase, "playing")
        self.assertEqual(sim.state(b)["game"]["turn"], sim.pid(b))


if __name__ == "__main__":
    unittest.main()

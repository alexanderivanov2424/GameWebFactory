"""TODO Game name: tests driven through the real lobby with gamekit.sim.Sim.

Copy to APP/games/<id>/tests/test_<id>.py. Run: python3 -I tools/run_tests.py <id>
"""

import unittest

from gamekit.sim import Sim

GAME = "TODO-game-id"


def new_game(players=2, **settings):
    sim = Sim(GAME, players=players, settings=settings or None)
    # If turn order is random, index players by it: [sim.index_of(pid) for pid in sim.game.queue.order()]
    return sim


class SettingsTests(unittest.TestCase):
    def test_clamped_and_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"rounds": "x"}}))  # TODO key


class PlayTests(unittest.TestCase):
    def test_not_your_turn(self):
        sim = new_game()
        # sim.fails(index, {"action": ...}, "not your turn")

    def test_hidden_info_not_leaked(self):
        sim = new_game()
        # Another player's state(i) and a spectator's must not contain your secrets.

    def test_game_end(self):
        sim = new_game()
        # Play to a win and to a draw/no winner; check sim.state(i)["result"].

    def test_player_leaves_mid_game(self):
        sim = new_game(players=3)
        sim.leave(0)
        # The game stays consistent (turn passes on) or finishes.


if __name__ == "__main__":
    unittest.main()

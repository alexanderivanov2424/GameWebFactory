"""{{GAME_NAME}}: tests. Run: python3 -I tools/run_tests.py {{GAME_ID}}

Two layers:
- Rules tests drive logic.Match directly (fast, no lobby): set up a position, act, check.
- Lobby tests go through the real lobby with gamekit.sim.Sim, the way browsers do: settings,
  turn checks, what each player and spectator receives, leaving mid-game.
"""

import importlib
import random
import unittest

from gamekit import LobbyError  # noqa: F401
from gamekit.sim import Sim

GAME = "{{GAME_ID}}"
Match = importlib.import_module(f"games.{GAME}.logic.match").Match  # the id may contain "-"


def new_match(players=2, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    return Match(names, {"rounds": 3, **settings}, rng=random.Random(1))  # TODO settings


def new_game(players=2, **settings):
    sim = Sim(GAME, players=players, settings=settings or None)
    # Turn order is random: index players by it with [sim.index_of(pid) for pid in sim.game.match.queue.order()]
    return sim


class RulesTests(unittest.TestCase):
    def test_turns_rotate(self):
        match = new_match()
        first = match.turn()
        match.move(first)
        self.assertNotEqual(match.turn(), first)

    def test_last_player_left_wins(self):
        match = new_match(players=3)
        order = match.queue.order()
        match.remove(order[0])
        match.remove(order[1])
        self.assertEqual(match.result["winner"], order[2])

    # TODO one test per rule: legal and illegal moves (assertRaises(LobbyError)), wins, draws.


class SettingsTests(unittest.TestCase):
    def test_clamped_and_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"rounds": "x"}}))  # TODO key


class LobbyTests(unittest.TestCase):
    def test_not_your_turn(self):
        sim = new_game()
        waiting = sim.index_of(sim.game.match.queue.order()[1])
        sim.fails(waiting, {"action": "move"}, "not your turn")  # TODO a real move

    def test_hidden_info_not_leaked(self):
        sim = new_game()
        # Another player's state(i) and a spectator's must not contain your secrets.

    def test_game_end(self):
        sim = new_game()
        # Play to a win and to a draw/no winner; check sim.state(i)["result"].

    def test_player_leaves_mid_game(self):
        sim = new_game()
        sim.leave(0)
        self.assertEqual(sim.state(1)["phase"], "finished")
        self.assertEqual(sim.state(1)["result"]["winner"], sim.pid(1))


if __name__ == "__main__":
    unittest.main()

"""Planet Jumpers: tests. Run: python3 -I tools/run_tests.py orbit-run

Two layers:
- Rules tests drive logic.Match directly (fast, no lobby): set up a position, act, check.
- Lobby tests go through the real lobby with gamekit.sim.Sim, the way browsers do: settings,
  turn checks, what each player and spectator receives, leaving mid-game.
"""

import importlib
import random
import unittest

from gamekit import LobbyError
from gamekit.sim import Sim

GAME = "orbit-run"
Match = importlib.import_module(f"games.{GAME}.logic.match").Match  # the id may contain "-"
Run = importlib.import_module(f"games.{GAME}.logic.ship").Run


def new_match(players=3):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    match = Match(names, Run.new(), rng=random.Random(1))
    match.start_mission()
    return match


class RulesTests(unittest.TestCase):
    def test_draft_turn_moves_on(self):
        match = new_match()
        first = match.turn()
        match.take(first, match.draft.left[0])
        self.assertNotEqual(match.turn(), first)

    def test_not_your_turn(self):
        match = new_match()
        waiting = next(pid for pid in match.seats if pid != match.turn())
        with self.assertRaises(LobbyError):
            match.take(waiting, match.draft.left[0])


class SettingsTests(unittest.TestCase):
    def test_validated(self):
        sim = Sim(GAME, players=3, start=False)
        self.assertIn("must be one of", sim.lobby(0, {"type": "settings", "settings": {"run": "x"}}))


class LobbyTests(unittest.TestCase):
    def test_not_your_turn(self):
        sim = Sim(GAME, players=3)
        match = sim.game.match
        waiting = sim.index_of(next(pid for pid in match.seats if pid != match.turn()))
        sim.fails(waiting, {"action": "take", "task": match.draft.left[0]}, "not your turn")

    def test_hidden_info_not_leaked(self):
        sim = Sim(GAME, players=3)
        hand = sim.state(0)["private"]["hand"]
        self.assertTrue(hand)
        self.assertNotEqual(sim.state(1)["private"]["hand"], hand)
        self.assertIsNone(sim.state(sim.spectator())["private"])

    def test_player_leaves_mid_game(self):
        sim = Sim(GAME, players=3)
        sim.leave(0)
        self.assertEqual(sim.state(1)["phase"], "finished")
        self.assertEqual(sim.state(1)["result"]["outcome"], "left")


if __name__ == "__main__":
    unittest.main()

"""Marooned: tests. Run: python3 -I tools/run_tests.py marooned

Two layers:
- Rules tests drive logic.Match directly (fast, no lobby): set up a position, act, check.
- Lobby tests go through the real lobby with gamekit.sim.Sim, the way browsers do: settings,
  turn checks, what each player and spectator receives, leaving mid-game.
Behaviour only: no checks on content (tile, card or objective files, counts, costs).
"""

import importlib
import random
import unittest

from gamekit import LobbyError
from gamekit.sim import Sim

GAME = "marooned"
Match = importlib.import_module(f"games.{GAME}.logic.match").Match


def new_match(players=4, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    match = Match(names, {"monsoon": 14, "objectivesDealt": 3, "objectivesKept": 2, **settings},
                  rng=random.Random(1))
    for pid in names:
        match.pick_objectives(pid, [o["id"] for o in match.private(pid)["dealt"]][:match.keep])
    return match


def new_game(players=4):
    sim = Sim(GAME, players=players)
    for i in range(players):
        dealt = sim.state(i)["private"]["dealt"]
        keep = sim.state(i)["game"]["rules"]["keep"]
        sim.ok(i, {"action": "keep", "objectives": [o["id"] for o in dealt][:keep]})
    return sim


class RulesTests(unittest.TestCase):
    def test_turns_go_round_then_night(self):
        match = new_match()
        first = match.turn()
        for _ in match.order:
            match.end_turn(match.turn())
        self.assertEqual(match.stage, "vote")
        for pid in match.order:
            match.vote(pid, "nobody")
        self.assertEqual((match.stage, match.day), ("day", 2))
        self.assertNotEqual(match.turn(), first)  # the first seat rotates

    def test_gather_report_never_better_than_the_roll(self):
        match = new_match()
        pid = match.turn()
        match.island.tile(match.island.camp)["res"]["wood"] = 9
        match.gather(pid, "wood")
        roll = match.pending["roll"]
        if roll < 6:
            with self.assertRaises(LobbyError):
                match.report(pid, roll + 1)
        match.report(pid, 1)
        self.assertEqual(match.people[pid].pack.get("wood", 0), 0)  # announced a 1: nothing
        self.assertEqual(match.people[pid].stats["lies"], 1 if roll > 1 else 0)

    def test_last_players_leaving_ends_the_game(self):
        match = new_match()
        match.remove("p1")
        self.assertIsNone(match.result)
        match.remove("p2")
        self.assertIsNotNone(match.result)


class SettingsTests(unittest.TestCase):
    def test_clamped_and_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"monsoon": "x"}}))


class LobbyTests(unittest.TestCase):
    def test_not_your_turn(self):
        sim = new_game()
        turn = sim.game.match.turn()
        waiting = next(i for i in range(4) if sim.pid(i) != turn)
        sim.fails(waiting, {"action": "end_turn"}, "not your turn")

    def test_hidden_info_not_leaked(self):
        sim = new_game()
        imposter = sim.game.match.imposter
        watcher = sim.spectator()
        for i in [*range(4), watcher]:
            state = sim.state(i)
            self.assertNotIn(imposter, str(state["game"].get("imposter", "")))
            self.assertNotIn("imposter", str(state["game"]))
        others = [i for i in range(4) if sim.pid(i) != imposter]
        for i in others:
            self.assertEqual(sim.state(i)["private"]["role"], "castaway")

    def test_player_leaves_mid_game(self):
        sim = new_game()
        sim.leave(0)
        self.assertEqual(sim.state(1)["phase"], "playing")
        sim.leave(1)
        self.assertEqual(sim.state(2)["phase"], "finished")


if __name__ == "__main__":
    unittest.main()

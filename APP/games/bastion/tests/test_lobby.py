"""Bastion: lobby tests through gamekit.sim.Sim (real messages, PatchState sync, hidden hands).
Uses the real content (the lobby doesn't take fixtures) but checks only behaviour.

Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

from gamekit.sim import Sim

helpers = importlib.import_module("games.bastion.tests.helpers")

GAME = "bastion"


def hand(sim, i):
    return sim.state(i)["private"]["hand"]


class LobbyTests(unittest.TestCase):
    def test_solo_game_starts(self):
        sim = Sim(GAME, players=1)
        self.assertEqual(sim.state(0)["phase"], "playing")
        self.assertEqual(sim.state(0)["game"]["stage"], "build")

    def test_settings_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"keepHealth": "x"}}))
        self.assertIn("one of", sim.lobby(0, {"type": "settings", "settings": {"difficulty": "brutal"}}))

    def test_hands_are_private(self):
        sim = Sim(GAME, players=2)
        watcher = sim.spectator()
        mine = hand(sim, 0)
        self.assertTrue(mine)
        self.assertNotEqual(sim.state(1)["private"]["hand"], mine)
        self.assertIsNone(sim.state(watcher).get("private"))
        self.assertEqual(sim.state(watcher)["game"]["seats"][sim.pid(0)]["hand"], len(mine))  # just the count

    def test_bad_messages_rejected(self):
        sim = Sim(GAME, players=2)
        sim.fails(0, {"action": "play", "uid": "x"}, "whole number")
        sim.fails(0, {"action": "play", "uid": 9999}, "isn't in your hand")
        sim.fails(0, {"action": "end_turn", "done": "yes"}, "true or false")
        sim.fails(0, {"action": "buy", "slot": 0}, "market is closed")
        sim.fails(0, {"action": "demolish"}, "Pick a structure")

    def test_play_by_message(self):
        helpers.install()
        try:
            sim = Sim(GAME, players=1)
            seat = sim.game.match.seats[sim.pid(0)]
            uid = helpers.give(sim.game.match, sim.pid(0), "t-tower")
            sim.fails(0, {"action": "play", "uid": uid}, "Pick where")
            target = next(iter(sim.game.match.private(sim.pid(0))["targets"]["t-tower"]))
            x, y = map(int, target.split(","))
            sim.ok(0, {"action": "play", "uid": uid, "x": x, "y": y})
            self.assertEqual(sim.state(0)["game"]["structures"][target]["card"], "t-tower")
            self.assertNotIn(uid, [c["uid"] for c in seat.hand])
        finally:
            helpers.remove()

    def test_full_level_flow_and_sync(self):
        sim = Sim(GAME, players=2)
        sim.ok(0, {"action": "end_turn"})
        sim.ok(0, {"action": "end_turn", "done": False})
        turns = sim.state(0)["game"]["levels"][0]["buildTurns"]
        for _ in range(turns):
            sim.ok(0, {"action": "end_turn"})
            sim.ok(1, {"action": "end_turn"})
        state = sim.state(1)  # patches applied the way lobby.js does
        game = state["game"]
        self.assertEqual(game["stage"], "market")
        self.assertEqual(game["battle"]["level"], 1)
        self.assertEqual(len(game["battle"]["frames"]), game["battle"]["ticks"])
        self.assertEqual(state["private"]["hand"], [])
        sim.ok(0, {"action": "ready"})
        sim.ok(1, {"action": "ready"})
        self.assertEqual(sim.state(0)["game"]["level"], 2)
        self.assertEqual(sim.state(0)["game"]["stage"], "build")

    def test_player_leaves_mid_game(self):
        sim = Sim(GAME, players=2)
        sim.ok(1, {"action": "end_turn"})
        sim.leave(1)
        self.assertEqual(sim.state(0)["phase"], "playing")
        self.assertNotIn(sim.pid(1), sim.state(0)["game"]["seats"])
        self.assertTrue(sim.state(0)["game"]["seats"][sim.pid(0)]["done"] is False)


if __name__ == "__main__":
    unittest.main()

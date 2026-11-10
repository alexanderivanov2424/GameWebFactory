"""Bastion: the lobby side through gamekit.sim.Sim (real content; never checks card details):
hidden hands, message validation, setup turns, the simultaneous phases, leaving.
Run: python3 -I tools/run_tests.py bastion
"""

import unittest

from gamekit.sim import Sim

# Three grass tiles in a row on the default map (valley), far apart for two players.
CITIES = [((10, 6), (11, 6), (12, 6)), ((10, 14), (11, 14), (12, 14))]


def set_up(sim, players, first=0):
    for i in range(first, players):
        for x, y in CITIES[i]:
            sim.ok(i, {"action": "setup", "x": x, "y": y})


class LobbyTests(unittest.TestCase):
    def test_hands_are_private(self):
        sim = Sim("bastion", players=2)
        spectator = sim.spectator()
        for i in (0, 1):  # each player gets their own hand, nobody else's
            own = [c["uid"] for c in sim.game.match.seats[sim.pid(i)].hand]
            self.assertEqual([c["uid"] for c in sim.state(i)["private"]["hand"]], own)
        self.assertIsNone(sim.state(spectator)["private"])
        for seat in sim.state(spectator)["game"]["seats"].values():
            self.assertNotIn("private", seat)

    def test_setup_takes_turns(self):
        sim = Sim("bastion", players=2)
        sim.fails(1, {"action": "setup", "x": 10, "y": 14}, "not your turn")
        set_up(sim, 1)
        self.assertEqual(sim.state(0)["game"]["setup"], {"pid": sim.pid(1), "kind": "keep"})
        set_up(sim, 2, first=1)
        game = sim.state(0)["game"]
        self.assertEqual((game["phase"], game["round"]), ("place", 1))

    def test_message_validation(self):
        sim = Sim("bastion", players=1)
        sim.fails(0, {"action": "setup"}, "Pick a tile")
        sim.fails(0, {"action": "setup", "x": 1}, "Row")
        set_up(sim, 1)
        sim.fails(0, {"action": "place", "x": 0, "y": 0}, "within 3 tiles")
        sim.fails(0, {"action": "ready", "done": "yes"}, "true or false")
        sim.fails(0, {"action": "play", "uid": 1}, "planning phase")
        sim.fails(0, {"action": "answer", "option": "road"}, "nothing to answer")
        sim.ok(0, {"action": "ready"})
        sim.fails(0, {"action": "play", "uid": "x"}, "Card")
        sim.fails(0, {"action": "play", "uid": 99999}, "isn't in your hand")
        sim.fails(0, {"action": "play", "uid": 1, "give": {"gems": 1}}, "Pick resources")
        sim.fails(0, {"action": "buy", "market": "shop", "slot": 0}, "blueprints or the actions")
        sim.fails(0, {"action": "reshuffle", "market": 1}, "blueprints or the actions")

    def test_spectators_cant_act(self):
        sim = Sim("bastion", players=1)
        spectator = sim.spectator()
        self.assertIsNotNone(sim.send(spectator, {"action": "ready"}))

    def test_round_runs_through_the_phases(self):
        sim = Sim("bastion", players=2)
        set_up(sim, 2)
        sim.ok(0, {"action": "ready"})
        self.assertEqual(sim.state(1)["game"]["phase"], "place")
        sim.ok(1, {"action": "ready"})  # nothing placed: no prompts, straight to planning
        self.assertEqual(sim.state(1)["game"]["phase"], "plan")
        sim.ok(0, {"action": "ready"})
        sim.ok(1, {"action": "ready"})
        game = sim.state(0)["game"]
        self.assertEqual((game["round"], game["phase"]), (2, "place"))
        self.assertFalse(game["seats"][sim.pid(0)]["ready"])

    def test_leaving_mid_game(self):
        sim = Sim("bastion", players=2)
        set_up(sim, 2)
        sim.ok(0, {"action": "ready"})
        sim.leave(1)  # the last one not ready left: the round moves on
        state = sim.state(0)
        self.assertEqual(list(state["game"]["seats"]), [sim.pid(0)])
        self.assertEqual(state["game"]["phase"], "plan")

    def test_last_player_leaving_ends_the_game(self):
        sim = Sim("bastion", players=1)
        spectator = sim.spectator()
        sim.leave(0)
        self.assertNotEqual(sim.state(spectator)["phase"], "playing")


if __name__ == "__main__":
    unittest.main()

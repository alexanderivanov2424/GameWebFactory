"""Bastion: the lobby side through gamekit.sim.Sim (real content; never checks card or enemy
details): hidden hands, message validation, rounds, leaving.
Run: python3 -I tools/run_tests.py bastion
"""

import unittest

from gamekit.sim import Sim


class LobbyTests(unittest.TestCase):
    def test_hands_are_private(self):
        sim = Sim("bastion", players=2)
        spectator = sim.spectator()
        for i in (0, 1):  # each player gets their own hand, nobody else's
            own = [c["uid"] for c in sim.game.match.seats[sim.pid(i)].hand]
            self.assertEqual([c["uid"] for c in sim.state(i)["private"]["hand"]], own)
            self.assertEqual(len(own), 5)
        self.assertIsNone(sim.state(spectator)["private"])
        for seat in sim.state(spectator)["game"]["seats"].values():
            self.assertEqual(seat["hand"], 5)  # only the size is public

    def test_message_validation(self):
        sim = Sim("bastion", players=1)
        sim.fails(0, {"action": "play", "uid": "x"}, "Card")
        sim.fails(0, {"action": "play", "uid": 99999}, "isn't in your hand")
        sim.fails(0, {"action": "play", "uid": 1, "x": 1}, "Row")
        sim.fails(0, {"action": "play", "uid": 1, "x": 1, "y": 1, "rotation": 4}, "Rotation")
        sim.fails(0, {"action": "strike", "foe": 0, "way": "magic"}, "soldiers or resources")
        sim.fails(0, {"action": "raze"}, "Pick a cell")
        sim.fails(0, {"action": "end_turn", "done": "yes"}, "true or false")

    def test_spectators_cant_act(self):
        sim = Sim("bastion", players=1)
        spectator = sim.spectator()
        self.assertIsNotNone(sim.send(spectator, {"action": "end_turn"}))

    def test_round_ends_when_everyone_is_done(self):
        sim = Sim("bastion", players=2)
        sim.ok(0, {"action": "end_turn"})
        self.assertTrue(sim.state(1)["game"]["seats"][sim.pid(0)]["done"])
        self.assertEqual(sim.state(1)["game"]["round"], 1)
        sim.ok(1, {"action": "end_turn"})
        self.assertEqual(sim.state(0)["game"]["round"], 2)
        self.assertFalse(sim.state(0)["game"]["seats"][sim.pid(0)]["done"])

    def test_leaving_mid_game(self):
        sim = Sim("bastion", players=2)
        sim.ok(1, {"action": "end_turn"})
        sim.leave(0)
        state = sim.state(1)
        self.assertEqual(list(state["game"]["seats"]), [sim.pid(1)])
        self.assertEqual(state["game"]["round"], 2)  # the one left was done: the round ended

    def test_last_player_leaving_ends_the_game(self):
        sim = Sim("bastion", players=1)
        spectator = sim.spectator()
        sim.leave(0)
        self.assertNotEqual(sim.state(spectator)["phase"], "playing")


if __name__ == "__main__":
    unittest.main()

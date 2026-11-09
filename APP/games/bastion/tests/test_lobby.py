"""Bastion: the lobby side through gamekit.sim.Sim (real content; never checks card or enemy
details): hidden hands, message validation, phases and turns, leaving.
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
        sim.fails(0, {"action": "place"}, "Pick a target")
        sim.fails(0, {"action": "place", "target": "fight99"}, "nothing there")
        sim.fails(0, {"action": "ready", "done": "yes"}, "true or false")
        sim.fails(0, {"action": "play", "uid": 1}, "Place your units first")
        sim.ok(0, {"action": "ready"})
        sim.fails(0, {"action": "resolve", "target": "haul", "tool": 1}, "true or false")
        sim.fails(0, {"action": "resolve", "target": "haul", "from": "x"}, "Haul source")
        sim.fails(0, {"action": "play", "uid": "x"}, "Card")
        sim.fails(0, {"action": "play", "uid": 99999}, "isn't in your hand")
        sim.fails(0, {"action": "play", "uid": 1, "x": 1}, "Row")
        sim.fails(0, {"action": "play", "uid": 1, "x": 1, "y": 1, "rotation": 4}, "Rotation")
        sim.fails(0, {"action": "strike", "foe": 0, "way": "magic"}, "soldiers or resources")
        sim.fails(0, {"action": "raze"}, "Pick a cell")

    def test_spectators_cant_act(self):
        sim = Sim("bastion", players=1)
        spectator = sim.spectator()
        self.assertIsNotNone(sim.send(spectator, {"action": "ready"}))

    def test_round_ends_after_every_turn(self):
        sim = Sim("bastion", players=2)
        sim.ok(0, {"action": "ready"})
        game = sim.state(1)["game"]
        self.assertEqual((game["phase"], game["ready"][sim.pid(0)]), ("place", True))
        sim.ok(1, {"action": "ready"})
        self.assertEqual((sim.state(1)["game"]["phase"], sim.state(1)["game"]["turn"]), ("act", sim.pid(0)))
        sim.fails(1, {"action": "end_turn"}, "turn")
        sim.ok(0, {"action": "end_turn"})
        self.assertEqual(sim.state(0)["game"]["turn"], sim.pid(1))
        sim.ok(1, {"action": "end_turn"})
        game = sim.state(0)["game"]
        self.assertEqual((game["round"], game["phase"], game["firstPlayer"]), (2, "place", sim.pid(1)))
        self.assertFalse(game["ready"][sim.pid(0)])

    def test_leaving_mid_game(self):
        sim = Sim("bastion", players=2)
        sim.ok(0, {"action": "ready"})
        sim.ok(1, {"action": "ready"})
        sim.leave(0)  # it was their turn: it passes
        state = sim.state(1)
        self.assertEqual(list(state["game"]["seats"]), [sim.pid(1)])
        self.assertEqual((state["game"]["round"], state["game"]["turn"]), (1, sim.pid(1)))

    def test_last_player_leaving_ends_the_game(self):
        sim = Sim("bastion", players=1)
        spectator = sim.spectator()
        sim.leave(0)
        self.assertNotEqual(sim.state(spectator)["phase"], "playing")


if __name__ == "__main__":
    unittest.main()

"""Smugglers: lobby tests through gamekit.sim.Sim (what each browser receives, turn checks,
leaving). Run: python3 -I tools/run_tests.py smugglers
"""

import json
import unittest

from gamekit.sim import Sim

GAME = "smugglers"


def new_game(players=3, **settings):
    return Sim(GAME, players=players, settings=settings or None)


def roles(sim):
    match = sim.game.match
    cop = sim.index_of(match.interpol.pid)
    first = sim.index_of(match.turn())
    return cop, first


class LobbyTests(unittest.TestCase):
    def test_settings_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"contractsEach": "x"}}))

    def test_not_your_turn(self):
        sim = new_game()
        cop, first = roles(sim)
        sim.fails(cop, {"action": "endTurn"}, "not your turn")
        sim.ok(first, {"action": "endTurn"})

    def test_bad_messages(self):
        sim = new_game()
        _, first = roles(sim)
        sim.fails(first, {"action": "move", "ship": ["s1"], "to": "kessar"}, "bad ship")
        sim.fails(first, {"action": "load", "load": "all", "discard": [], "declare": "titan-ore"}, "bad load")
        sim.fails(first, {"action": "play", "card": "x"}, "pick a card")
        sim.fails(first, {"action": "nope"})

    def test_move_through_the_lobby(self):
        sim = new_game()
        _, first = roles(sim)
        mine = sim.state(first)["private"]
        ship = next(iter(mine["reach"]))
        to = next(iter(mine["reach"][ship]))
        sim.ok(first, {"action": "move", "ship": ship, "to": to})
        self.assertEqual(sim.state(first)["game"]["ships"][ship]["at"], to)

    def test_hidden_information(self):
        sim = new_game()
        cop, first = roles(sim)
        match = sim.game.match
        other = next(i for i in range(3) if i not in (cop, first))
        hand = match.smugglers[sim.pid(first)]["hand"]
        self.assertEqual(sim.state(first)["private"]["hand"], hand)
        self.assertEqual(sim.state(first)["private"]["role"], "smuggler")
        self.assertEqual(sim.state(cop)["private"]["role"], "interpol")
        watcher = sim.spectator()
        self.assertIsNone(sim.state(watcher).get("private"))
        public = json.dumps(sim.state(watcher)["game"])
        self.assertNotIn('"uid"', public)  # no card instances (hands, cargo, Interpol's hand)
        self.assertNotIn('"uid"', json.dumps(sim.state(other)["private"]["cargo"]))  # empty ships
        self.assertNotIn(json.dumps(hand), json.dumps(sim.state(other)))
        self.assertNotIn(json.dumps(match.interpol.hand), json.dumps(sim.state(first)))

    def test_interpol_turn_and_patches(self):
        sim = new_game()
        cop, _ = roles(sim)
        match = sim.game.match
        while match.turn() != match.interpol.pid:
            sim.ok(sim.index_of(match.turn()), {"action": "endTurn"})
        hand = sim.state(cop)["private"]["hand"]
        funding = [c["uid"] for c in hand if c["card"] == "funding"]
        for uid in funding:
            sim.ok(cop, {"action": "play", "card": uid})
        self.assertEqual(sim.state(cop)["game"]["police"]["budget"], 2 * len(funding))
        sim.ok(cop, {"action": "endTurn"})
        self.assertEqual(sim.state(0)["game"]["round"], 2)
        self.assertEqual(sim.state(1)["game"], sim.state(2)["game"])  # patches applied the same

    def test_player_leaves_mid_game(self):
        sim = new_game(players=2)
        cop, smuggler = roles(sim)
        sim.leave(cop)
        state = sim.state(smuggler)
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["result"]["winner"], sim.pid(smuggler))


if __name__ == "__main__":
    unittest.main()

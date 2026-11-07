"""Block Blast: lobby tests through gamekit.sim.Sim, the way browsers do: settings, turn checks,
what each player and spectator receives, game end, leaving mid-game.
Run: python3 -I tools/run_tests.py block-blast
"""

import importlib
import json
import unittest

from gamekit.sim import Sim

helpers = importlib.import_module("games.block-blast.tests.helpers")  # the id contains "-"
GAME, fill, row_cells = helpers.GAME, helpers.fill, helpers.row_cells


class SettingsTests(unittest.TestCase):
    def test_clamped_and_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"health": "x"}}))
        sim.lobby(0, {"type": "settings", "settings": {"health": 500}})
        self.assertEqual(sim.state(0)["settings"]["health"], 50)


class LobbyTests(unittest.TestCase):
    def new_game(self, players=2, **settings):
        sim = Sim(GAME, players=players, settings=settings or None)
        order = [sim.index_of(pid) for pid in sim.game.match.queue.order()]
        return sim, order

    def test_settings_apply(self):
        sim, order = self.new_game(health=3)
        seats = sim.state(0)["game"]["seats"]
        self.assertEqual([seats[sim.pid(i)]["gold"] for i in order], [1, 2])
        self.assertEqual(seats[sim.pid(0)]["health"], 3)

    def test_not_your_turn_and_bad_messages(self):
        sim, (first, second) = self.new_game()
        uid = sim.state(second)["private"]["hand"][0]["uid"]
        sim.fails(second, {"action": "place", "uid": uid, "rotation": 0, "row": 0, "col": 0}, "not your turn")
        uid = sim.state(first)["private"]["hand"][0]["uid"]
        sim.fails(first, {"action": "place", "uid": uid, "rotation": True, "row": 0, "col": 0}, "whole number")
        sim.fails(first, {"action": "place", "uid": uid, "rotation": 4, "row": 0, "col": 0}, "Rotation")
        sim.fails(first, {"action": "place", "uid": uid, "rotation": 0, "row": 9, "col": 0}, "Row")
        sim.fails(first, {"action": "buy", "slot": 5}, "Slot")
        sim.fails(first, {"action": "fly"}, "")
        sim.ok(first, {"action": "place", "uid": uid, "rotation": 0, "row": 0, "col": 0})
        sim.ok(second, {"action": "aim", "player": sim.pid(first)})
        sim.game.match.seats[sim.pid(second)].chapels = 1
        uid2 = sim.state(second)["private"]["hand"][0]["uid"]
        sim.ok(second, {"action": "remove", "uid": uid2})  # off-turn removal is allowed
        self.assertEqual(len(sim.state(second)["private"]["hand"]), 2)
        self.assertEqual(sim.state(first)["game"]["seats"][sim.pid(second)]["chapels"], 0)
        sim.ok(first, {"action": "buy", "slot": 0})
        sim.ok(first, {"action": "end_turn"})
        self.assertEqual(sim.state(first)["game"]["turn"], sim.pid(second))

    def test_hidden_info_not_leaked(self):
        sim, (first, second) = self.new_game()
        watcher = sim.spectator()
        match = sim.game.match
        for i in (first, second):  # each player gets exactly their own hand
            self.assertEqual(sim.state(i)["private"]["hand"], match.seats[sim.pid(i)].hand)
        self.assertIsNone(sim.state(watcher)["private"])
        public = sim.state(watcher)["game"]
        for pid in (sim.pid(first), sim.pid(second)):
            self.assertEqual(public["seats"][pid]["hand"], 3)  # a count, not the cards
        self.assertNotIn("uid", json.dumps(public["seats"]))

    def test_game_end(self):
        sim, (first, second) = self.new_game(health=1)
        match = sim.game.match
        fill(match, sim.pid(first), row_cells(0, skip=(0,)), "A")
        uid = sim.state(first)["private"]["hand"][0]["uid"]
        sim.ok(first, {"action": "patch", "uid": uid, "row": 0, "col": 0})
        state = sim.state(second)
        self.assertEqual(state["phase"], "finished")
        self.assertEqual(state["result"]["winner"], sim.pid(first))

    def test_player_leaves_mid_game(self):
        sim, (first, second) = self.new_game()
        sim.leave(first)
        self.assertEqual(sim.state(second)["phase"], "finished")
        self.assertEqual(sim.state(second)["result"]["winner"], sim.pid(second))

    def test_three_players_one_leaves(self):
        sim, order = self.new_game(players=3)
        sim.leave(order[0])
        state = sim.state(order[1])
        self.assertEqual(state["phase"], "playing")
        self.assertEqual(state["game"]["turn"], sim.pid(order[1]))
        self.assertTrue(state["game"]["seats"][sim.pid(order[0])]["out"])


if __name__ == "__main__":
    unittest.main()

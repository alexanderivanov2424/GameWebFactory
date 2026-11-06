"""sync.py: merge patches, FullState (unchanged messages) and PatchState (keyframes + patches)."""

import unittest

from gamekit import LobbyGame, PatchState
from gamekit.sim import Sim
from gamekit.sync import merge_apply, merge_diff, quantize


class MergePatchTests(unittest.TestCase):
    CASES = [
        ({"a": 1, "b": 2}, {"a": 1, "b": 3}),
        ({"a": {"x": 1, "y": 2}}, {"a": {"x": 1}}),
        ({"a": [1, 2]}, {"a": [1, 2, 3]}),
        ({"a": 1}, {"a": {"deep": {"er": 1}}}),
        ({"a": {"b": 1}}, {"a": 5}),
        (None, {"a": 1}),
        ({"a": 1}, None),
        ({}, {"p1": {"x": 1.5, "y": 2}, "p2": {"x": 0, "y": 0}}),
    ]

    def test_round_trip(self):
        for old, new in self.CASES:
            with self.subTest(old=old, new=new):
                self.assertEqual(merge_apply(old, merge_diff(old, new)), new)

    def test_patch_has_only_changes(self):
        old = {"p1": {"x": 1, "y": 2}, "p2": {"x": 5, "y": 5}, "gone": 1}
        new = {"p1": {"x": 1, "y": 3}, "p2": {"x": 5, "y": 5}}
        self.assertEqual(merge_diff(old, new), {"p1": {"y": 3}, "gone": None})

    def test_apply_does_not_modify(self):
        doc = {"a": {"b": 1}}
        merge_apply(doc, {"a": {"b": 2}})
        self.assertEqual(doc, {"a": {"b": 1}})

    def test_quantize(self):
        self.assertEqual(quantize(1.2345, 0.1), 1.2)
        self.assertEqual(quantize(7.6, 1), 8)
        self.assertIsInstance(quantize(7.6, 1), int)


class Board(LobbyGame):
    """A big public board, one secret per player, and an action that changes one cell."""

    ACTIONS = {"set": "set", "noop": "noop"}

    def start_game(self):
        self.cells = {i: 0 for i in range(100)}
        self.secrets = {p.id: f"secret-{p.id}" for p in self.players}

    def set(self, member, data):
        self.cells[data["cell"]] = data["value"]

    def noop(self, member, data):
        pass

    def game_state(self):
        return {"cells": self.cells}

    def private_state(self, member):
        secret = self.secrets.get(member.id)
        return {"secret": secret} if secret else None


class PatchBoard(Board):
    SYNC = PatchState


class FullStateTests(unittest.TestCase):
    def test_messages_keep_their_shape(self):
        sim = Sim(Board, players=2)
        sim.ok(0, {"action": "set", "cell": 3, "value": 1})
        message = sim.messages(1)[-1]
        self.assertEqual(list(message), [
            "type", "phase", "hostId", "settings", "settingsSpec", "gameNumber", "minPlayers",
            "maxPlayers", "startBlocker", "players", "spectators", "game", "result", "you", "private",
        ])
        self.assertEqual(message["game"]["cells"]["3"], 1)
        self.assertEqual(message["private"], {"secret": f"secret-{sim.pid(1)}"})
        self.assertTrue(all(m["type"] == "state" for m in sim.messages(1)))


class PatchStateTests(unittest.TestCase):
    def setUp(self):
        self.sim = Sim(PatchBoard, players=2)
        self.watcher = self.sim.spectator()

    def test_change_sends_only_the_cell(self):
        sim = self.sim
        sim.ok(0, {"action": "set", "cell": 42, "value": 7})
        patch = sim.messages(1)[-1]
        self.assertEqual(patch["type"], "patch")
        self.assertEqual(patch["g"], {"cells": {"42": 7}})
        self.assertNotIn("p", patch)
        self.assertEqual(sim.state(1)["game"]["cells"]["42"], 7)
        self.assertEqual(sim.state(self.watcher)["game"]["cells"]["42"], 7)
        self.assertEqual(sim.state(1)["private"], {"secret": f"secret-{sim.pid(1)}"})

    def test_no_change_sends_nothing(self):
        sim = self.sim
        before = len(sim.messages(1))
        sim.ok(0, {"action": "noop"})
        self.assertEqual(len(sim.messages(1)), before)

    def test_private_never_leaks(self):
        sim = self.sim
        sim.game.secrets[sim.pid(0)] = "changed"
        sim.ok(0, {"action": "noop"})
        self.assertEqual(sim.messages(0)[-1]["p"], {"secret": "changed"})
        for index in (1, self.watcher):
            self.assertNotIn("changed", str(sim.messages(index)))
        self.assertIsNone(sim.state(self.watcher)["private"])

    def test_lobby_change_sends_full_state(self):
        sim = self.sim
        sim.lobby(1, {"type": "name", "name": "Renamed"})
        message = sim.messages(0)[-1]
        self.assertEqual(message["type"], "state")
        self.assertEqual(len(message["game"]["cells"]), 100)

    def test_reconnect_and_resync_send_full_state(self):
        sim = self.sim
        sim._run(sim.game.on_reconnect(sim.clients[1]))
        self.assertEqual(sim.messages(1)[-1]["type"], "state")
        sim.lobby(0, {"type": "resync"})
        self.assertEqual(sim.messages(0)[-1]["type"], "state")
        sim.ok(0, {"action": "set", "cell": 1, "value": 2})
        self.assertEqual(sim.messages(0)[-1]["type"], "patch")
        self.assertEqual(sim.state(0)["game"]["cells"]["1"], 2)

    def test_back_to_lobby_and_new_game(self):
        sim = self.sim
        sim.game.finish({"winner": None})
        sim.lobby(0, {"type": "back_to_lobby"})
        self.assertEqual(sim.state(1)["phase"], "lobby")
        self.assertIsNone(sim.state(1)["game"])
        sim.start()
        self.assertEqual(sim.state(1)["phase"], "playing")
        self.assertEqual(sim.state(1)["gameNumber"], 2)


if __name__ == "__main__":
    unittest.main()

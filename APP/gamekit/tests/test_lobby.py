"""LobbyGame: joining, host, ready/start, settings schema, ACTIONS dispatch, game numbers, timers."""

import unittest

from gamekit import FINISHED, LOBBY, PLAYING, Int, LobbyError, LobbyGame
from gamekit.sim import Sim


class Counter(LobbyGame):
    MIN_PLAYERS = 2
    MAX_PLAYERS = 3
    SETTINGS = {
        "size": Int("Size", default=4, low=2, high=8),
        "goal": Int("Goal", default=3, low=1, high="size"),
    }
    ACTIONS = {"add": "add", "slow": "slow", "end": "end"}

    def start_game(self):
        self.total = 0
        self.ticks = 0

    def reset_game(self):
        self.total = 0

    def add(self, member, data):
        if data.get("n") == 0:
            raise LobbyError("Zero does nothing.")
        self.total += 1

    async def slow(self, member, data):  # async handlers work too
        self.total += 10
        self.schedule(1, self.tick)

    def tick(self):
        self.ticks += 1

    def end(self, member, data):
        self.finish({"winner": member.id})

    def game_state(self):
        return {"total": self.total}


class LobbyTests(unittest.TestCase):
    def test_host_is_first_player_and_passes_on_leave(self):
        sim = Sim(Counter, players=3, start=False)
        self.assertEqual(sim.game.host_id, sim.pid(0))
        sim.leave(0)
        self.assertEqual(sim.game.host_id, sim.pid(1))

    def test_full_game_rejects_join(self):
        sim = Sim(Counter, players=3, start=False)
        extra = sim.spectator()
        self.assertEqual(sim.lobby(extra, {"type": "join"}), "The game is full.")

    def test_start_needs_ready_and_host(self):
        sim = Sim(Counter, players=2, start=False)
        self.assertIn("ready", sim.lobby(0, {"type": "start"}).lower())
        sim.lobby(0, {"type": "ready", "ready": True})
        sim.lobby(1, {"type": "ready", "ready": True})
        self.assertEqual(sim.lobby(1, {"type": "start"}), "Only the host can do that.")
        self.assertIsNone(sim.lobby(0, {"type": "start"}))
        self.assertEqual(sim.game.phase, PLAYING)

    def test_min_players(self):
        sim = Sim(Counter, players=1, start=False)
        sim.lobby(0, {"type": "ready", "ready": True})
        self.assertEqual(sim.state(0)["startBlocker"], "Need at least 2 players.")


class SettingsTests(unittest.TestCase):
    def test_defaults_and_spec(self):
        sim = Sim(Counter, start=False)
        state = sim.state(0)
        self.assertEqual(state["settings"], {"size": 4, "goal": 3})
        spec = {s["key"]: s for s in state["settingsSpec"]}
        self.assertEqual(spec["size"]["min"], 2)
        self.assertEqual(spec["goal"]["maxFrom"], "size")

    def test_clamp_linked_bound_and_partial_update(self):
        sim = Sim(Counter, start=False)
        self.assertIsNone(sim.lobby(0, {"type": "settings", "settings": {"size": 99, "goal": 99}}))
        self.assertEqual(sim.game.settings, {"size": 8, "goal": 8})
        sim.lobby(0, {"type": "settings", "settings": {"size": 3}})
        self.assertEqual(sim.game.settings, {"size": 3, "goal": 3})

    def test_rejects_non_integers_and_non_hosts(self):
        sim = Sim(Counter, start=False)
        self.assertEqual(sim.lobby(0, {"type": "settings", "settings": {"size": "5"}}), "Size must be a whole number.")
        self.assertEqual(sim.lobby(0, {"type": "settings", "settings": {"size": True}}), "Size must be a whole number.")
        self.assertEqual(sim.lobby(1, {"type": "settings", "settings": {"size": 5}}), "Only the host can do that.")


class ActionTests(unittest.TestCase):
    def test_dispatch_errors_and_unknown(self):
        sim = Sim(Counter)
        sim.ok(0, {"action": "add"})
        sim.fails(1, {"action": "add", "n": 0}, "zero does nothing")
        sim.fails(0, {"action": "nope"}, "unknown action")
        self.assertEqual(sim.state(1)["game"], {"total": 1})

    def test_async_handler_and_timers(self):
        sim = Sim(Counter, auto_timers=False)
        sim.ok(0, {"action": "slow"})
        self.assertEqual(sim.game.total, 10)
        self.assertEqual(len(sim.pending_timers()), 1)
        sim.run_timers()
        self.assertEqual(sim.game.ticks, 1)

    def test_spectators_cannot_act(self):
        sim = Sim(Counter)
        watcher = sim.spectator()
        self.assertIn("not playing", sim.send(watcher, {"action": "add"}))


class GameNumberTests(unittest.TestCase):
    def test_counts_games_and_returns_to_lobby(self):
        sim = Sim(Counter)
        self.assertEqual(sim.state(0)["gameNumber"], 1)
        sim.ok(0, {"action": "end"})
        self.assertEqual(sim.game.phase, FINISHED)
        self.assertEqual(sim.state(1)["result"], {"winner": sim.pid(0)})
        sim.lobby(0, {"type": "back_to_lobby"})
        self.assertEqual(sim.game.phase, LOBBY)
        sim.start()
        self.assertEqual(sim.state(1)["gameNumber"], 2)

    def test_client_ids_never_sent(self):
        sim = Sim(Counter)
        text = repr(sim.state(1))
        for client in sim.clients:
            self.assertNotIn(client.id, text)


if __name__ == "__main__":
    unittest.main()

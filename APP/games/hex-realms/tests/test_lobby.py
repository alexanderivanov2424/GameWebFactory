"""Hex Realms: lobby tests through gamekit.sim.Sim (what each player sees, the timer, leaving)."""

import unittest

from gamekit.sim import Sim

GAME = "hex-realms"


def hall_of(sim, i):
    m = sim.game.match
    return next(s for s in m.structures.values() if s["owner"] == sim.pid(i) and s["type"] == "town_hall")


class LobbyTests(unittest.TestCase):
    def test_settings_validated(self):
        sim = Sim(GAME, start=False)
        self.assertIn("whole number", sim.lobby(0, {"type": "settings", "settings": {"turns": "x"}}))

    def test_orders_stay_secret_until_the_turn_resolves(self):
        sim = Sim(GAME, players=2, settings={"seed": 3})
        hall = hall_of(sim, 0)
        sim.ok(0, {"action": "recruit", "structure": hall["id"], "kind": "militia"})
        mine, theirs, watcher = sim.state(0), sim.state(1), sim.state(sim.spectator())
        self.assertEqual(len(mine["private"]["orders"]["recruits"]), 1)
        self.assertEqual(theirs["private"]["orders"]["recruits"], [])
        self.assertIsNone(watcher.get("private"))
        public = theirs["game"]["players"][sim.pid(0)]
        self.assertEqual(public["res"]["gold"], 10)  # the start-of-turn stock, not after paying
        self.assertLess(mine["private"]["res"]["gold"], 10)

    def test_everyone_done_resolves(self):
        sim = Sim(GAME, players=2, settings={"seed": 3})
        sim.ok(0, {"action": "done", "done": True})
        self.assertEqual(sim.state(1)["game"]["turn"], 1)
        self.assertTrue(sim.state(1)["game"]["players"][sim.pid(0)]["done"])
        sim.ok(1, {"action": "done", "done": True})
        self.assertEqual(sim.state(0)["game"]["turn"], 2)

    def test_bad_messages_are_refused(self):
        sim = Sim(GAME, players=2, settings={"seed": 3})
        sim.fails(0, {"action": "build", "kind": "road", "at": 5, "rot": 0}, "Missing at")
        sim.fails(0, {"action": "move", "unit": "u999", "to": "0,0"}, "not your unit")
        theirs = next(u for u, x in sim.game.match.units.items() if x["owner"] == sim.pid(1))
        sim.fails(0, {"action": "disband", "unit": theirs}, "not your unit")

    def test_turn_timer_ends_the_turn(self):
        sim = Sim(GAME, players=2, settings={"seed": 3, "turnSeconds": 30}, auto_timers=False)
        self.assertEqual(len(sim.pending_timers()), 1)
        sim.step()
        self.assertEqual(sim.state(0)["game"]["turn"], 2)
        self.assertEqual(len(sim.pending_timers()), 1)  # the next turn's timer

    def test_solo_game_plays_to_the_turn_limit(self):
        sim = Sim(GAME, players=1, settings={"seed": 3, "turns": 10})
        for turn in range(1, 11):
            self.assertEqual(sim.state(0)["game"]["turn"], turn)
            sim.ok(0, {"action": "done", "done": True})
        result = sim.state(0)["result"]
        self.assertEqual(result["winner"], sim.pid(0))
        self.assertIn("points", result["reason"])

    def test_player_leaves_mid_game(self):
        sim = Sim(GAME, players=2, settings={"seed": 3})
        sim.leave(0)
        self.assertEqual(sim.state(1)["phase"], "finished")
        self.assertEqual(sim.state(1)["result"]["winner"], sim.pid(1))


if __name__ == "__main__":
    unittest.main()

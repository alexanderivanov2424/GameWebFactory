"""Hex Realms: lobby tests through gamekit.sim.Sim (what each player sees, the timer, leaving)."""

import unittest

from gamekit.sim import Sim

GAME = "hex-realms"


class LobbyTests(unittest.TestCase):
    def test_orders_stay_secret_until_the_turn_resolves(self):
        sim = Sim(GAME, players=2, settings={"seed": 3})
        settlers = next(u for u, x in sim.game.match.units.items() if x["owner"] == sim.pid(0))
        sim.ok(0, {"action": "found", "unit": settlers, "rot": sim.state(0)["private"]["found"][settlers][0]})
        mine, theirs, watcher = sim.state(0), sim.state(1), sim.state(sim.spectator())
        self.assertEqual(list(mine["private"]["orders"]["found"]), [settlers])
        self.assertEqual(theirs["private"]["orders"]["found"], {})
        self.assertNotIn("orders", watcher["private"])

    def test_turn_timer_ends_the_turn(self):
        sim = Sim(GAME, players=2, settings={"seed": 3, "turnSeconds": 30}, auto_timers=False)
        self.assertEqual(len(sim.pending_timers()), 1)
        sim.step()
        self.assertEqual(sim.state(0)["game"]["turn"], 2)
        self.assertEqual(len(sim.pending_timers()), 1)  # the next turn's timer

    def test_bots_take_seats_and_end_their_turn_at_once(self):
        sim = Sim(GAME, players=1, settings={"seed": 3, "bots": 2})
        game = sim.state(0)["game"]
        self.assertEqual(game["seats"], [sim.pid(0), "b1", "b2"])
        self.assertEqual(game["bots"], ["b1", "b2"])
        self.assertTrue(game["players"]["b1"]["done"] and game["players"]["b2"]["done"])
        self.assertFalse(game["players"][sim.pid(0)]["done"])
        self.assertTrue(sim.game.match.orders["b1"]["found"])  # their Settlers found a city on turn 1
        self.assertNotIn("b1", str(sim.state(0)["private"]["orders"]))  # bot orders stay secret
        sim.ok(0, {"action": "done", "done": True})
        self.assertEqual(sim.state(0)["game"]["turn"], 2)


if __name__ == "__main__":
    unittest.main()

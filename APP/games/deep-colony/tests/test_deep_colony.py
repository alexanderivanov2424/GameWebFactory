"""Deep Colony: lobby tests (gamekit.sim.Sim). Rules tests are in the other test_*.py files.
Run: python3 -I tools/run_tests.py deep-colony
"""

import unittest

from gamekit.sim import Sim

GAME = "deep-colony"


def new_game(players=2):
    return Sim(GAME, players=players, settings={"mapSize": "small", "colonists": 2})


def dig_target(sim):
    """A diggable cell (any solid that isn't bedrock)."""
    world = sim.game.match.world
    for y in range(2, world.h - 2):
        for x in range(2, world.w - 2):
            i = world.idx(x, y)
            if world.is_solid(i) and world.element_id(i) != "bedrock":
                return x, y
    raise AssertionError("no diggable cell")


class LobbyTests(unittest.TestCase):
    def test_any_player_pauses_and_sets_speed(self):
        sim = new_game()
        sim.ok(1, {"action": "pause", "paused": True})
        sim.tick(1)  # real-time games send changes with the next tick
        self.assertTrue(sim.state(0)["game"]["clock"]["paused"])
        sim.ok(0, {"action": "speed", "speed": 3})
        sim.tick(1)
        self.assertEqual(sim.state(1)["game"]["clock"]["speed"], 3)
        sim.fails(0, {"action": "speed", "speed": 4}, "Speed must be")

    def test_paused_colony_does_not_advance(self):
        sim = new_game()
        sim.ok(0, {"action": "pause", "paused": True})
        before = sim.game.match.time
        sim.tick(5)
        self.assertEqual(sim.game.match.time, before)

    def test_speed_runs_more_steps_per_tick(self):
        sim = new_game()
        sim.ok(0, {"action": "speed", "speed": 2})
        before = sim.game.match.time
        sim.tick(1)
        self.assertAlmostEqual(sim.game.match.time - before, 2 / sim.game.TICK_RATE)

    def test_orders_show_who_gave_them_to_everyone(self):
        sim = new_game()
        x, y = dig_target(sim)
        sim.ok(1, {"action": "dig", "rect": [x, y, x, y]})
        sim.tick(1)
        i = str(sim.game.match.world.idx(x, y))
        self.assertEqual(sim.state(0)["game"]["digs"][i]["by"], sim.pid(1))

    def test_spectator_cannot_order(self):
        sim = new_game()
        spectator = sim.spectator()
        sim.fails(spectator, {"action": "pause", "paused": True}, "not playing")

    def test_cursor_input_is_shown_to_everyone(self):
        sim = new_game()
        sim.input(0, {"cursor": [3, 4], "tool": "dig"})
        sim.tick(1)
        player = sim.state(1)["game"]["players"][sim.pid(0)]
        self.assertEqual((player["cursor"], player["tool"]), ([3, 4], "dig"))

    def test_bad_input_rejected(self):
        sim = new_game()
        sim.input(0, {"cursor": ["a", 4]})
        sim.tick(1)
        self.assertNotIn("cursor", sim.state(1)["game"]["players"][sim.pid(0)])

    def test_only_host_ends(self):
        sim = new_game()
        sim.fails(1, {"action": "end"}, "Only the host")
        sim.ok(0, {"action": "end"})
        self.assertEqual(sim.state(1)["phase"], "finished")

    def test_colony_ends_when_every_colonist_died(self):
        sim = new_game()
        match = sim.game.match
        match._had_dupes = True
        match.dupes.clear()
        sim.tick(1)
        self.assertEqual(sim.state(0)["phase"], "finished")


if __name__ == "__main__":
    unittest.main()

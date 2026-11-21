"""Snowbound: tests. Run: python3 -I tools/run_tests.py snowbound

Rules tests drive logic.Match directly on a small valley; lobby tests use gamekit.sim.Sim.
"""

import importlib
import random
import unittest

from gamekit import LobbyError
from gamekit.sim import Sim

GAME = "snowbound"
Match = importlib.import_module(f"games.{GAME}.logic.match").Match


def new_match(players=1, **settings):
    names = {f"p{i + 1}": f"Player {i + 1}" for i in range(players)}
    return Match(names, {"mapSize": "small", "goal": 75, **settings}, rng=random.Random(1))


def frontier_lot(match):
    """A workable lot that isn't a feature (so clearing it finds nothing)."""
    world = match.world
    return next(i for i in sorted(world.targets) if world.kind[i] == "plain")


class RulesTests(unittest.TestCase):
    def test_click_digs_and_pays(self):
        match = new_match()
        world, p = match.world, match.players["p1"]
        i = frontier_lot(match)
        before = world.snow[i]
        removed = match.click("p1", *world.xy(i))
        self.assertEqual(removed, 1)
        self.assertAlmostEqual(world.snow[i], before - 1)
        self.assertEqual(p.cash, 1)

    def test_click_far_from_cleared_ground_does_nothing(self):
        match = new_match()
        self.assertEqual(match.click("p1", 0, 0), 0)
        self.assertEqual(match.players["p1"].cash, 0)

    def test_clearing_a_lot_opens_its_neighbours(self):
        match = new_match()
        world = match.world
        i = frontier_lot(match)
        world.snow[i] = 0.5
        match.click("p1", *world.xy(i))
        self.assertTrue(world.reached[i])
        self.assertNotIn(i, world.targets)
        for j in world.neighbours(i):
            if not world.reached[j]:
                self.assertIn(j, world.targets)

    def test_machines_clear_snow_on_their_own(self):
        match = new_match()
        p = match.players["p1"]
        p.owned["helper"] = 5
        for _ in range(50):
            match.step(0.1)
        self.assertGreater(p.cleared, 0)
        self.assertGreater(p.cash, 0)

    def test_diesel_machines_stop_without_diesel(self):
        match = new_match()
        p = match.players["p1"]
        p.owned["snowblower"] = 3
        p.diesel = 0
        match.step(0.1)
        self.assertEqual(match.crews["p1:snowblower"].state, "stalled")
        self.assertEqual(p.cleared, 0)

    def test_cold_stove_gives_frostbite_and_stops_clicking(self):
        match = new_match()
        p = match.players["p1"]
        match.woodpile = 0
        p.warmth = 0.01
        match.step(0.1)
        self.assertTrue(p.frostbite)
        with self.assertRaises(LobbyError):
            match.click("p1", *match.world.xy(frontier_lot(match)))

    def test_ration_eaten_when_hungry(self):
        match = new_match()
        p = match.players["p1"]
        p.food, p.rations = 50, 1
        match.step(0.1)
        self.assertEqual(p.rations, 0)
        self.assertGreater(p.food, 75)

    def test_no_diesel_or_logs_bought_in_a_blizzard(self):
        match = new_match()
        match.players["p1"].cash = 10_000
        match.weather.kind = "blizzard"
        with self.assertRaises(LobbyError):
            match.supply("p1", "logs", 10)
        with self.assertRaises(LobbyError):
            match.supply("p1", "diesel", 10)
        match.supply("p1", "rations", 1)

    def test_shared_upgrade_bought_once_for_everyone(self):
        match = new_match(players=2)
        a, b = match.players["p1"], match.players["p2"]
        a.cash = a.earned = b.earned = 10 ** 6
        match.upgrade("p1", "road-salt")
        self.assertEqual(match.shared_upgrades, {"road-salt": "p1"})
        self.assertFalse(b.upgrade_visible("road-salt", match.shared_upgrades))

    def test_machine_prices_grow(self):
        match = new_match()
        p = match.players["p1"]
        p.cash = 10 ** 6
        cash = p.cash
        match.buy("p1", "helper", 1)
        first = cash - p.cash
        cash = p.cash
        match.buy("p1", "helper", 1)
        self.assertGreater(cash - p.cash, first)


class LobbyTests(unittest.TestCase):
    def test_spectator_cannot_dig_and_gets_no_private_state(self):
        sim = Sim(GAME, players=1, settings={"mapSize": "small"})
        s = sim.spectator()
        sim.fails(s, {"action": "click", "x": 1, "y": 1}, "not playing")
        sim.tick(1)
        self.assertIsNone(sim.state(s).get("private"))
        self.assertIn("machines", sim.state(0)["private"])

    def test_bad_messages_rejected(self):
        sim = Sim(GAME, players=1, settings={"mapSize": "small"})
        sim.fails(0, {"action": "buy", "machine": ["x"], "count": 1}, "Unknown machine")
        sim.fails(0, {"action": "buy", "machine": "helper", "count": 3}, "Buy 1 or 10")
        sim.fails(0, {"action": "click", "x": "1", "y": 2}, "Bad lot")
        sim.fails(0, {"action": "supply", "item": "logs", "qty": 1.5}, "whole number")

    def test_last_player_leaving_stops_the_game(self):
        sim = Sim(GAME, players=2, settings={"mapSize": "small"})
        sim.leave(0)
        self.assertEqual(sim.state(1)["phase"], "playing")
        sim.leave(1)
        self.assertNotEqual(sim.game.phase, "playing")


if __name__ == "__main__":
    unittest.main()

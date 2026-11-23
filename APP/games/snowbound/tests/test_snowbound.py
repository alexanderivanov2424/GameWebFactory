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


def stand_next_to(match, pid, i):
    """Put pid's character on the reached lot next to lot i."""
    world, p = match.world, match.players[pid]
    j = next(j for j in world.neighbours(i) if world.reached[j])
    p.x, p.y = world.xy(j)[0] + 0.5, world.xy(j)[1] + 0.5


class RulesTests(unittest.TestCase):
    def test_swing_digs_and_pays(self):
        match = new_match()
        world, p = match.world, match.players["p1"]
        i = frontier_lot(match)
        stand_next_to(match, "p1", i)
        before = world.snow[i]
        removed = match.swing("p1", *world.xy(i))
        self.assertEqual(removed, 1)
        self.assertAlmostEqual(world.snow[i], before - 1)
        self.assertEqual(p.cash, 1)

    def test_swing_far_from_cleared_ground_does_nothing(self):
        match = new_match()
        self.assertEqual(match.swing("p1", 0, 0), 0)
        self.assertEqual(match.players["p1"].cash, 0)

    def test_cannot_shovel_out_of_reach(self):
        match = new_match()
        i = frontier_lot(match)
        match.players["p1"].x += 20
        self.assertEqual(match.swing("p1", *match.world.xy(i)), 0)

    def test_deep_snow_blocks_walking(self):
        match = new_match()
        world, p = match.world, match.players["p1"]
        i = frontier_lot(match)
        stand_next_to(match, "p1", i)
        x, y = world.xy(i)
        match.set_input("p1", [{(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}[
            (x - int(p.x), y - int(p.y))]], None, False)
        for _ in range(20):
            match.step(0.1)
        self.assertNotEqual((int(p.x), int(p.y)), (x, y))

    def test_warm_only_near_heat(self):
        match = new_match()
        p = match.players["p1"]
        p.warmth = 50
        match.step(1)
        self.assertGreater(p.warmth, 50)  # starts at the cabin
        p.x += 30
        p.warmth = 50
        match.step(1)
        self.assertLess(p.warmth, 50)

    def test_hut_keeps_you_warm_away_from_the_cabin(self):
        match = new_match()
        world, p = match.world, match.players["p1"]
        far = max(world.reached_list, key=lambda i: abs(world.xy(i)[0] - world.cx))
        world.reached[far] = 1
        p.x, p.y = world.xy(far)[0] + 0.5, world.xy(far)[1] + 0.5
        match.huts.append(world.xy(far))
        p.warmth = 50
        match.step(1)
        self.assertGreater(p.warmth, 50)

    def test_clearing_a_lot_opens_its_neighbours(self):
        match = new_match()
        world = match.world
        i = frontier_lot(match)
        world.snow[i] = 0.5
        stand_next_to(match, "p1", i)
        match.swing("p1", *world.xy(i))
        self.assertTrue(world.reached[i])
        self.assertNotIn(i, world.targets)
        for j in world.neighbours(i):
            if not world.reached[j]:
                self.assertIn(j, world.targets)

    def test_machines_clear_snow_on_their_own(self):
        match = new_match()
        p = match.players["p1"]
        p.cash = 1000
        match.buy("p1", "kid", 5)
        self.assertEqual(sum(u.pid == "p1" for u in match.units.values()), 5)
        p.cash = 0
        for _ in range(50):
            match.step(0.1)
        self.assertGreater(p.cleared, 0)
        self.assertGreater(sum(u.load for u in match.units.values()), 0)  # carried home, paid there

    def test_diesel_machines_stop_without_diesel(self):
        match = new_match()
        p = match.players["p1"]
        p.cash = 10_000
        match.buy("p1", "dozer", 1)
        p.diesel = 0
        match.step(0.1)
        self.assertEqual(next(iter(match.units.values())).state, "stalled")
        self.assertEqual(p.cleared, 0)

    def test_cold_stove_gives_frostbite_and_stops_shoveling(self):
        match = new_match()
        p = match.players["p1"]
        match.woodpile = 0
        p.warmth = 0.01
        match.step(0.1)
        self.assertTrue(p.frostbite)
        i = frontier_lot(match)
        stand_next_to(match, "p1", i)
        self.assertEqual(match.swing("p1", *match.world.xy(i)), 0)

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

    def test_dog_tunnels_and_leaves_road(self):
        match = new_match()
        p = match.players["p1"]
        p.cash = 1000
        match.buy("p1", "dog", 1)
        for _ in range(300):
            match.step(0.1)
        self.assertGreater(match.world.road_count, 0)

    def test_dozer_shoves_snow_outward(self):
        match = new_match()
        world, p = match.world, match.players["p1"]
        p.cash, p.diesel = 10 ** 6, 1000
        match.buy("p1", "dozer", 1)
        total_before = sum(world.snow)
        for _ in range(50):
            match.step(0.1)
        removed = total_before - sum(world.snow)
        self.assertGreater(p.cleared, 0)
        self.assertLess(removed, p.cleared * 2)  # 60% of what it dug is still out there
        self.assertLess(p.cleared, removed + 1e-6)

    def test_brazier_melts_around_it_and_keeps_you_warm(self):
        match = new_match()
        world, p = match.world, match.players["p1"]
        far = max((i for i in world.reached_list if world.kind[i] != "cabin"),
                  key=lambda i: abs(world.xy(i)[0] - world.cx))
        x, y = world.xy(far)
        p.x, p.y, p.cash = x + 0.5, y + 0.5, 10 ** 6
        with self.assertRaises(LobbyError):
            match.buy("p1", "brazier", 10)
        match.buy("p1", "brazier", 1)
        with self.assertRaises(LobbyError):
            match.buy("p1", "brazier", 1)  # one per spot
        p.x += 20
        p.cash = 0
        match.step(1)
        self.assertGreater(p.cash, 0)
        p.x -= 20
        p.warmth = 50
        match.step(1)
        self.assertGreater(p.warmth, 50)

    def test_machine_prices_grow(self):
        match = new_match()
        p = match.players["p1"]
        p.cash = 10 ** 6
        cash = p.cash
        match.buy("p1", "kid", 1)
        first = cash - p.cash
        cash = p.cash
        match.buy("p1", "kid", 1)
        self.assertGreater(cash - p.cash, first)


class LobbyTests(unittest.TestCase):
    def test_spectator_cannot_dig_and_gets_no_shop(self):
        sim = Sim(GAME, players=1, settings={"mapSize": "small"})
        s = sim.spectator()
        sim.fails(s, {"action": "rally", "x": 1, "y": 1}, "not playing")
        sim.tick(1)
        self.assertNotIn("machines", sim.state(s)["private"])
        self.assertIn("machines", sim.state(0)["private"])

    def test_bad_messages_rejected(self):
        sim = Sim(GAME, players=1, settings={"mapSize": "small"})
        sim.fails(0, {"action": "buy", "machine": ["x"], "count": 1}, "Unknown machine")
        sim.fails(0, {"action": "buy", "machine": "kid", "count": 3}, "Buy 1 or 10")
        sim.fails(0, {"action": "rally", "x": "1", "y": 2}, "Bad lot")
        self.assertIn("Bad keys", sim.input(0, {"keys": ["jump"]}))
        sim.fails(0, {"action": "supply", "item": "logs", "qty": 1.5}, "whole number")

    def test_last_player_leaving_stops_the_game(self):
        sim = Sim(GAME, players=2, settings={"mapSize": "small"})
        sim.leave(0)
        self.assertEqual(sim.state(1)["phase"], "playing")
        sim.leave(1)
        self.assertNotEqual(sim.game.phase, "playing")


if __name__ == "__main__":
    unittest.main()

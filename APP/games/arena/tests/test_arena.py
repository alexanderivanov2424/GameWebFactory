"""Arena tests: movement, clamping, input validation, ping display, end action, leaving."""

import unittest

from gamekit.sim import Sim

STEP = 220 / 20  # units per tick


def dot(sim, i, who=None):
    return sim.state(i)["game"]["dots"][sim.pid(i if who is None else who)]


class ArenaTests(unittest.TestCase):
    def test_initial_positions_inside_and_distinct(self):
        sim = Sim("arena", players=16)
        dots = sim.state(0)["game"]["dots"]
        self.assertEqual(len(dots), 16)
        self.assertEqual(len({(d["x"], d["y"]) for d in dots.values()}), 16)
        self.assertEqual(len({d["color"] for d in dots.values()}), 16)
        pts = list(dots.values())
        for d in pts:
            self.assertTrue(18 <= d["x"] <= 782 and 18 <= d["y"] <= 482)
        for a in range(16):
            for b in range(a):
                dist = ((pts[a]["x"] - pts[b]["x"]) ** 2 + (pts[a]["y"] - pts[b]["y"]) ** 2) ** 0.5
                self.assertGreater(dist, 36)
        self.assertEqual(sim.state(0)["game"]["arena"], {"w": 800, "h": 500, "r": 18})

    def test_move_right(self):
        sim = Sim("arena", players=1)
        x0 = dot(sim, 0)["x"]
        y0 = dot(sim, 0)["y"]
        sim.input(0, {"keys": ["right"]})
        sim.tick(5)
        d = dot(sim, 0)
        self.assertAlmostEqual(d["x"], x0 + 5 * STEP, delta=0.2)
        self.assertEqual(d["y"], y0)

    def test_diagonal_normalized_and_opposites_cancel(self):
        sim = Sim("arena", players=2)
        x0, y0 = dot(sim, 0)["x"], dot(sim, 0)["y"]
        sim.input(0, {"keys": ["right", "down"]})
        sim.input(1, {"keys": ["left", "right"]})
        p1 = dict(dot(sim, 1))
        sim.tick(4)
        d = dot(sim, 0)
        dist = ((d["x"] - x0) ** 2 + (d["y"] - y0) ** 2) ** 0.5
        self.assertAlmostEqual(dist, 4 * STEP, delta=0.5)
        self.assertEqual((dot(sim, 1)["x"], dot(sim, 1)["y"]), (p1["x"], p1["y"]))

    def test_clamped_at_every_edge(self):
        for key, axis, expected in (("left", "x", 18), ("right", "x", 782),
                                    ("up", "y", 18), ("down", "y", 482)):
            sim = Sim("arena", players=1)
            sim.input(0, {"keys": [key]})
            sim.tick(100)
            self.assertEqual(dot(sim, 0)[axis], expected, key)

    def test_bad_inputs_rejected(self):
        sim = Sim("arena", players=1)
        for bad in ({"keys": ["jump"]}, {"keys": "up"}, {}, {"keys": ["up", "up"]},
                    {"keys": ["up", "down", "left", "right", "up"]}, {"keys": [1]}):
            self.assertEqual(sim.input(0, bad), "Bad input.", bad)
        self.assertIsNone(sim.input(0, {"keys": []}))
        self.assertIsNone(sim.input(0, {"keys": ["up", "down", "left", "right"]}))

    def test_spectator_input_ignored(self):
        sim = Sim("arena", players=1)
        s = sim.spectator()
        x0 = dot(sim, 0)["x"]
        sim.input(s, {"keys": ["right"]})
        sim.tick(3)
        self.assertEqual(dot(sim, 0)["x"], x0)
        self.assertEqual(len(sim.state(0)["game"]["dots"]), 1)

    def test_name_color_ping(self):
        sim = Sim("arena", players=2)
        d = dot(sim, 0)
        self.assertNotIn("ping", d)
        self.assertEqual(d["name"], sim.state(0)["players"][0]["name"])
        self.assertTrue(d["color"].startswith("#"))
        self.assertNotEqual(d["color"], dot(sim, 1)["color"])
        sim.ping(0, 42)
        sim.tick(1)
        self.assertEqual(dot(sim, 0)["ping"], 42)
        self.assertNotIn("ping", dot(sim, 1))

    def test_host_ends_round(self):
        sim = Sim("arena", players=2)
        sim.fails(1, {"action": "end"}, "Only the host")
        self.assertEqual(sim.state(0)["phase"], "playing")
        sim.ok(0, {"action": "end"})
        st = sim.state(1)
        self.assertEqual(st["phase"], "finished")
        self.assertEqual(st["result"], {"reason": "The host ended the round."})

    def test_player_leaves_mid_game(self):
        sim = Sim("arena", players=3)
        gone = sim.pid(1)
        sim.leave(1)
        sim.input(2, {"keys": ["right"]})
        x0 = dot(sim, 0, 0)["x"]
        sim.tick(2)
        dots = sim.state(0)["game"]["dots"]
        self.assertNotIn(gone, dots)
        self.assertEqual(len(dots), 2)
        self.assertEqual(sim.state(0)["phase"], "playing")
        self.assertEqual(dots[sim.pid(0)]["x"], x0)


if __name__ == "__main__":
    unittest.main()

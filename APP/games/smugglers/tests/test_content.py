"""Smugglers: the board and content files. Run: python3 -I tools/run_tests.py smugglers"""

import importlib
import json
import random
import tempfile
import unittest
from pathlib import Path

GAME = "games.smugglers.logic"
board_mod = importlib.import_module(f"{GAME}.board")
content = importlib.import_module(f"{GAME}.content")
BOARD = board_mod.BOARDS["outer-rim"]


def write(folder, name, data):
    (Path(folder) / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


SMALL = {
    "name": "Tiny", "width": 400, "height": 300,
    "planets": {"a": {"name": "A", "color": "#ff0000", "x": 10, "y": 10},
                "b": {"name": "B", "color": "#00ff00", "x": 300, "y": 10},
                "c": {"name": "C", "color": "#0000ff", "x": 150, "y": 250}},
    "routes": {"r1": {"from": "a", "to": "b", "length": 4},
               "r2": {"from": "r1.2", "to": "c", "length": 2},
               "r3": {"from": "a", "to": "c", "length": 2}},
    "starts": ["a"], "interpolHome": "c",
}


class FirstBoardTests(unittest.TestCase):
    def test_fifteen_named_planets_with_distinct_colors(self):
        self.assertEqual(len(BOARD.planets), 15)
        colors = [p["color"].lower() for p in BOARD.planets.values()]
        names = [p["name"] for p in BOARD.planets.values()]
        self.assertEqual(len(set(colors)), 15)
        self.assertEqual(len(set(names)), 15)

    def test_routes_two_to_five_long_and_connected(self):
        raw = json.loads((board_mod.CONTENT / "boards" / "outer-rim.json").read_text())
        lengths = [r["length"] for r in raw["routes"].values()]
        self.assertTrue(all(2 <= n <= 5 for n in lengths))
        self.assertTrue(BOARD.connected(BOARD.nodes))

    def test_has_routes_from_dots(self):
        raw = json.loads((board_mod.CONTENT / "boards" / "outer-rim.json").read_text())
        dot_ends = [r for r in raw["routes"].values() if "." in r["from"] or "." in r["to"]]
        self.assertTrue(any("." in r["from"] and "." in r["to"] for r in dot_ends))  # dot to dot

    def test_public_is_json(self):
        data = json.loads(json.dumps(BOARD.public()))
        self.assertEqual(len(data["nodes"]), len(BOARD.nodes))


class BoardTests(unittest.TestCase):
    def load(self, data, bad=False):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, "tiny", data)
            if not bad:
                return board_mod.load_boards(Path(folder))
            with self.assertLogs("smugglers", "ERROR"):
                return board_mod.load_boards(Path(folder))

    def test_dots_and_branches(self):
        board = self.load(SMALL)["tiny"]
        self.assertEqual(sorted(n for n in board.nodes if not board.is_planet(n)), ["r1.1", "r1.2", "r1.3", "r2.1", "r3.1"])
        self.assertEqual(board.nodes["r1.2"], (155, 10))  # half way from a to b
        self.assertIn("r2.1", board.neighbours("r1.2"))
        self.assertEqual(board.distance("b", "c"), 4)  # b, r1.3, r1.2, r2.1, c

    def test_reach_blocked_and_stops(self):
        board = self.load(SMALL)["tiny"]
        self.assertEqual(board.reach("a", 2), {"r1.1": 1, "r1.2": 2, "r3.1": 1, "c": 2})
        self.assertNotIn("r1.2", board.reach("a", 3, blocked={"r1.1"}))
        reach = board.reach("a", 4, stops={"r1.1"})
        self.assertIn("r1.1", reach)
        self.assertNotIn("r1.2", set(board.reach("a", 4, stops={"r1.1"}, blocked={"r3.1"})))

    def test_bad_boards_are_skipped(self):
        same_color = json.loads(json.dumps(SMALL))
        same_color["planets"]["b"]["color"] = "#FF0000"
        self.assertEqual(self.load(same_color, bad=True), {})
        unknown = json.loads(json.dumps(SMALL))
        unknown["routes"]["r2"]["from"] = "r9.1"
        self.assertEqual(self.load(unknown, bad=True), {})
        apart = json.loads(json.dumps(SMALL))
        del apart["routes"]["r2"], apart["routes"]["r3"]
        self.assertEqual(self.load(apart, bad=True), {})


class ContentTests(unittest.TestCase):
    def test_goods(self):
        legal = [g for g in content.GOODS.values() if g["legal"]]
        illegal = [g for g in content.GOODS.values() if not g["legal"]]
        self.assertEqual({g["value"] for g in legal}, {1, 2, 3})
        self.assertEqual({g["value"] for g in illegal}, {7, 8, 9})
        self.assertGreater(sum(g["count"] for g in legal), 5 * sum(g["count"] for g in illegal))
        self.assertTrue(all(g["penalty"] > 0 for g in illegal))

    def test_ships_and_interpol_cards(self):
        self.assertTrue(all(3 <= s["speed"] <= 5 for s in content.SHIPS.values()))
        starting = sum(card["start"] for card in content.INTERPOL_CARDS.values())
        self.assertEqual(starting, 5)
        pieces = {c["effects"].get("piece") for c in content.INTERPOL_CARDS.values()}
        self.assertTrue({"patrol", "barrier", "checkpoint"} <= pieces)

    def test_contracts_ask_for_legal_goods_far_enough(self):
        contracts = content.make_contracts(BOARD, content.GOODS, 30, random.Random(3))
        self.assertEqual(len(contracts), 30)
        for c in contracts:
            self.assertTrue(content.GOODS[c["good"]]["legal"])
            self.assertGreaterEqual(BOARD.distance(c["from"], c["to"]), content.MIN_CONTRACT_DISTANCE)
            self.assertGreaterEqual(c["bonus"], 1)

    def test_bad_interpol_card_is_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            write(folder, "bad", {"name": "Bad", "kind": "action", "cost": 1, "supply": 1,
                                  "effects": {"piece": "tank"}})
            write(folder, "good", {"name": "Good", "kind": "funding", "cost": 1, "supply": 1,
                                   "effects": {"budget": 1}})
            with self.assertLogs("smugglers", "ERROR"):
                cards = content.load_interpol_cards(Path(folder))
        self.assertEqual(list(cards), ["good"])


if __name__ == "__main__":
    unittest.main()

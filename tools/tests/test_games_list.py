"""tools/games_list.py: the home page's game list and its player-count labels."""

import importlib
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "tools_games_list", Path(__file__).resolve().parent.parent / "games_list.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

GAMES_DIR = Path(__file__).resolve().parent.parent.parent / "APP" / "games"


class LabelTests(unittest.TestCase):
    def test_range(self):
        self.assertEqual(tool.players_label(2, 4), "2–4")

    def test_exact_count(self):
        self.assertEqual(tool.players_label(2, 2), "2")

    def test_no_cap_shows_plus(self):
        self.assertEqual(tool.players_label(1, 16), "1+")


class ListTests(unittest.TestCase):
    def test_every_game_listed_with_its_class_limits(self):
        games = tool.build(GAMES_DIR)
        self.assertEqual({g["id"] for g in games}, {p.parent.name for p in GAMES_DIR.glob("*/game.json")})
        for entry in games:
            game = importlib.import_module(f"games.{entry['id']}.server").Game
            self.assertEqual(entry["players"], tool.players_label(game.MIN_PLAYERS, game.MAX_PLAYERS))


if __name__ == "__main__":
    unittest.main()

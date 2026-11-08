"""Bastion: content loader tests (cards, enemies, levels, maps) on inline data, never the real files.

Run: python3 -I tools/run_tests.py bastion
"""

import importlib
import unittest

cards = importlib.import_module("games.bastion.logic.cards")
enemies = importlib.import_module("games.bastion.logic.enemies")
maps = importlib.import_module("games.bastion.logic.maps")

TOWER = {"name": "T", "icon": "T", "kind": "tower", "labor": 2, "cost": 3, "stats": {"damage": [1, 2, 3], "range": 2}}
MAP = {"name": "M", "terrain": ["....", "....", "....", "...."], "keep": [0, 1],
       "roads": {"main": [[3, 1], [0, 1]], "flank": [[2, 2], [2, 1], [0, 1]]}}


class CardTests(unittest.TestCase):
    def test_stats_per_level(self):
        card = cards.parse_card("t", TOWER)
        self.assertEqual(card["place"], "ground")
        self.assertEqual(cards.stat(card, "damage", 2), 2)
        self.assertEqual(cards.stat(card, "range", 3), 2)
        self.assertEqual(cards.stat(card, "missing", 1, default=7), 7)

    def test_unknown_stat_or_kind_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown stat"):
            cards.parse_card("t", {**TOWER, "stats": {"hp": 5}})
        with self.assertRaisesRegex(ValueError, "kind"):
            cards.parse_card("t", {**TOWER, "kind": "moat"})
        with self.assertRaisesRegex(ValueError, "list of 3"):
            cards.parse_card("t", {**TOWER, "stats": {"damage": [1, 2]}})

    def test_targeted_orders(self):
        order = cards.parse_card("o", {"name": "O", "icon": "O", "kind": "order", "labor": 1, "cost": 1,
                                       "stats": {"upgrade": True}})
        self.assertEqual(order["place"], "structure")
        self.assertEqual(order["maxLevel"], 1)


class EnemyAndLevelTests(unittest.TestCase):
    def test_enemy_defaults_and_abilities(self):
        enemy = enemies.parse_enemy("e", {"name": "E", "icon": "E", "hp": 5, "speed": 0.2,
                                          "heal": {"amount": 1, "radius": 1, "every": 2}})
        self.assertEqual(enemy["armor"], 0)
        self.assertFalse(enemy["flying"])
        self.assertEqual(enemy["heal"]["every"], 2)

    def test_level_needs_known_enemies_and_roads(self):
        known = {"e": {}}
        with self.assertRaisesRegex(ValueError, "enemy"):
            enemies.parse_level("l", {"name": "L", "waves": [{"enemy": "x", "count": 1}]}, known)
        with self.assertRaisesRegex(ValueError, "road"):
            enemies.parse_level("l", {"name": "L", "waves": [{"enemy": "e", "count": 1, "road": "sky"}]}, known)
        level = enemies.parse_level("l", {"name": "L", "waves": [{"enemy": "e", "count": 2, "road": "flank"}]}, known)
        self.assertEqual(enemies.public_level(level)["counts"], {"e": 2})
        self.assertEqual(enemies.public_level(level)["roads"], ["flank"])


class MapTests(unittest.TestCase):
    def test_roads_expand_and_merge(self):
        game_map = maps.parse_map("m", MAP)
        self.assertEqual(game_map.roads["main"], [(3, 1), (2, 1), (1, 1), (0, 1)])
        self.assertEqual(game_map.roads["flank"][:2], [(2, 2), (2, 1)])
        self.assertEqual(game_map.entrances, {(3, 1), (2, 2)})
        self.assertEqual(game_map.remaining[(2, 1)], 2)

    def test_bad_roads_refused(self):
        with self.assertRaisesRegex(ValueError, "straight"):
            maps.parse_map("m", {**MAP, "roads": {**MAP["roads"], "main": [[3, 2], [0, 1]]}})
        with self.assertRaisesRegex(ValueError, "keep"):
            maps.parse_map("m", {**MAP, "roads": {**MAP["roads"], "main": [[3, 1], [1, 1]]}})
        with self.assertRaisesRegex(ValueError, "exactly"):
            maps.parse_map("m", {**MAP, "roads": {"main": MAP["roads"]["main"]}})


if __name__ == "__main__":
    unittest.main()

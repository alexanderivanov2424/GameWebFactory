"""Block Blast: card packs (logic/packs.py, cards/packs/): the loader,
the pool a Match deals its market from, and the lobby setting.
Run: python3 -I tools/run_tests.py block-blast
"""

import importlib
import json
import logging
import random
import tempfile
import unittest
from pathlib import Path

from gamekit.sim import Sim

helpers = importlib.import_module("games.block-blast.tests.helpers")  # the id contains "-"
packs = importlib.import_module("games.block-blast.logic.packs")
CARDS = importlib.import_module("games.block-blast.logic.cards").CARDS


class LoaderTests(unittest.TestCase):
    def test_bad_packs_skipped(self):
        files = {
            "good": {"name": "Good", "description": "Fine", "cards": {"dagger": 2, "nope": 1}},
            "bad-no-name": {"cards": {"dagger": 1}},
            "bad-empty": {"name": "Empty", "cards": {}},
            "bad-cards": {"name": "List", "cards": ["dagger"]},
        }
        with tempfile.TemporaryDirectory() as folder:
            for name, data in files.items():
                Path(folder, f"{name}.json").write_text(json.dumps(data))
            with self.assertLogs("block-blast", logging.ERROR):
                loaded = packs.load_packs(Path(folder), CARDS)
        self.assertEqual(list(loaded), ["good"])
        self.assertEqual(loaded["good"]["cards"], {"dagger": 2})  # the unknown card is left out

    def test_pool_counts_every_selected_pack(self):
        two = {"a": {"cards": {"dagger": 2}}, "b": {"cards": {"dagger": 1, "pair": 1}}}
        self.assertEqual(sorted(packs.pool(["a", "b"], two)), ["dagger"] * 3 + ["pair"])
        self.assertEqual(packs.pool(["b"], two), ["dagger", "pair"])


class MatchPackTests(unittest.TestCase):
    def test_market_dealt_from_selected_packs_only(self):
        match = helpers.new_match(packs=["siege", "goblin"])
        dealt = [c["card"] for c in match.market.slots] + [c["card"] for c in match.market.deck.draw_pile]
        self.assertEqual(sorted(dealt), sorted(packs.pool(["siege", "goblin"], packs.PACKS)))
        self.assertEqual(set(dealt), set(packs.PACKS["siege"]["cards"]) | set(packs.PACKS["goblin"]["cards"]))

    def test_small_pool_leaves_slots_empty(self):
        tiny = {"tiny": {"cards": {"dagger": 2, "pair": 1}}}  # 3 cards for a market of 10
        settings = {**helpers.SETTINGS, "packs": ["tiny"], "market": "cost", "costSize": 10}
        match = helpers.Match({"p1": "A", "p2": "B"}, settings, rng=random.Random(1), packs=tiny)
        self.assertEqual(sum(1 for s in match.market.slots if s), 3)
        self.assertEqual(len(match.market.deck), 0)


class LobbyPackTests(unittest.TestCase):
    def test_setting(self):
        sim = Sim(helpers.GAME, start=False)
        spec = {s["key"]: s for s in sim.state(0)["settingsSpec"]}["packs"]
        self.assertEqual((spec["type"], spec["min"]), ("multi", 1))
        self.assertIn("pick at least 1", sim.lobby(0, {"type": "settings", "settings": {"packs": []}}))
        self.assertIsNone(sim.lobby(0, {"type": "settings", "settings": {"packs": ["siege", "base"]}}))
        self.assertEqual(sim.state(0)["settings"]["packs"], ["base", "siege"])

    def test_game_uses_the_packs(self):
        sim = Sim(helpers.GAME, players=2, settings={"packs": ["chapel"], "market": "cost", "costSize": 10})
        slots = sim.state(0)["game"]["market"]["slots"]
        self.assertLessEqual({s["card"] for s in slots if s}, set(packs.PACKS["chapel"]["cards"]))


if __name__ == "__main__":
    unittest.main()

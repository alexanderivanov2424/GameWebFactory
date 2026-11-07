"""Block Blast: card packs (logic/packs.py, cards/packs/): what each real pack holds, the loader,
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


class RealPackTests(unittest.TestCase):
    def test_packs_and_what_they_hold(self):
        self.assertEqual(list(packs.PACKS), ["base", "chapel", "goblin", "siege"])
        self.assertEqual(sum(len(packs.pool([p], packs.PACKS)) for p in packs.PACKS), 49)
        for pack_id, pack in packs.PACKS.items():
            self.assertTrue(pack["name"] and pack["description"], pack_id)
            for card_id in pack["cards"]:
                card = CARDS[card_id]
                kind = ("goblin" if card["tile"] == "goblin" else "siege" if "siege" in card["symbols"]
                        else "chapel" if "chapel" in card["symbols"] else "base")
                self.assertEqual(kind, pack_id, card_id)

    def test_starter_cards_are_in_no_pack(self):
        in_packs = {card_id for pack in packs.PACKS.values() for card_id in pack["cards"]}
        self.assertFalse(in_packs & set(importlib.import_module("games.block-blast.logic.cards").STARTING_DECK))


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
        self.assertEqual(len(dealt), 9)
        self.assertEqual(set(dealt), set(packs.PACKS["siege"]["cards"]) | set(packs.PACKS["goblin"]["cards"]))

    def test_small_pool_leaves_slots_empty(self):
        match = helpers.new_match(packs=["siege"], market="cost")  # 3 cards for a market of 10
        self.assertEqual(sum(1 for s in match.market.slots if s), 3)
        self.assertEqual(len(match.market.deck), 0)


class LobbyPackTests(unittest.TestCase):
    def test_setting(self):
        sim = Sim(helpers.GAME, start=False)
        spec = {s["key"]: s for s in sim.state(0)["settingsSpec"]}["packs"]
        self.assertEqual((spec["type"], spec["min"]), ("multi", 1))
        self.assertEqual([o["label"] for o in spec["options"]], ["Base cards", "Chapel cards", "Goblin cards", "Siege cards"])
        self.assertIn("pick at least 1", sim.lobby(0, {"type": "settings", "settings": {"packs": []}}))
        self.assertIsNone(sim.lobby(0, {"type": "settings", "settings": {"packs": ["siege", "base"]}}))
        self.assertEqual(sim.state(0)["settings"]["packs"], ["base", "siege"])

    def test_game_uses_the_packs(self):
        sim = Sim(helpers.GAME, players=2, settings={"packs": ["chapel"], "market": "cost", "costSize": 10})
        slots = sim.state(0)["game"]["market"]["slots"]
        self.assertEqual(sorted(s["card"] for s in slots if s), ["chapel", "chapel", "shrine", "shrine"])


if __name__ == "__main__":
    unittest.main()

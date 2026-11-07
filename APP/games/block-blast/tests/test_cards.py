"""Block Blast: tile types, symbols, the card loader and rotating cards."""

import importlib
import json
import logging
import tempfile
import unittest
from pathlib import Path

GAME = "games.block-blast.logic"
cards = importlib.import_module(f"{GAME}.cards")
tiles = importlib.import_module(f"{GAME}.tiles")
symbols = importlib.import_module(f"{GAME}.symbols")
effects = importlib.import_module(f"{GAME}.effects")


def positions(piece):
    return {(dr, dc) for dr, dc, _, _ in piece}


def mirrored(piece, width):
    return {(dr, width - 1 - dc) for dr, dc, _, _ in piece}


class RegistryTests(unittest.TestCase):
    def test_every_symbol_has_an_effect_and_unique_codes(self):
        self.assertEqual(set(effects.EFFECTS), set(symbols.SYMBOLS))
        codes = [s.code for s in symbols.SYMBOLS.values()]
        self.assertEqual(len(set(codes)), len(codes))
        self.assertTrue(all(code.isupper() and len(code) == 1 for code in codes))
        self.assertTrue(all(name == s.name for name, s in symbols.SYMBOLS.items()))
        art_only = [name for name, effect in effects.EFFECTS.items() if effect is effects.decorative]
        self.assertEqual(art_only, ["goblin"])

    def test_tile_codes(self):
        codes = [t.code for t in tiles.TILE_TYPES.values()]
        self.assertEqual(len(set(codes)), len(codes))
        self.assertTrue(all(code.islower() and len(code) == 1 for code in codes))
        self.assertNotIn(cards.CARD_TILE, codes)
        self.assertTrue(tiles.TILE_TYPES["goblin"].spoils)
        self.assertTrue(tiles.TILE_TYPES["grey"].unspoilable)
        self.assertIn(tiles.DEFAULT_TILE, tiles.TILE_TYPES)


class RotationTests(unittest.TestCase):
    def test_rotations_fit_5x5_and_keep_tiles_and_symbols(self):
        for card in cards.CARDS.values():
            base = sorted(((t, s) for _, _, t, s in card["pieces"][0]), key=repr)
            for piece, (h, w) in zip(card["pieces"], card["sizes"]):
                self.assertLessEqual(max(h, w), 5, card["id"])
                self.assertTrue(all(0 <= dr < h and 0 <= dc < w for dr, dc, _, _ in piece), card["id"])
                self.assertEqual(sorted(((t, s) for _, _, t, s in piece), key=repr), base, card["id"])
            back, _, _ = cards.rotate(card["pieces"][3], *card["sizes"][3])
            self.assertEqual(sorted(back, key=repr), sorted(card["pieces"][0], key=repr), card["id"])

    def test_rotation_never_mirrors(self):
        hook = cards.CARDS["hook"]  # an L with the attack at the bend, never a J
        h, w = hook["sizes"][0]
        self.assertNotIn(mirrored(hook["pieces"][0], w), [positions(p) for p in hook["pieces"]])
        self.assertEqual(cards.public(hook)["rotations"][1], {"tiles": ["bbb", "b.."], "symbols": ["A..", "..."]})


class LoaderTests(unittest.TestCase):
    def load(self, files):
        with tempfile.TemporaryDirectory() as folder:
            for name, data in files.items():
                Path(folder, f"{name}.json").write_text(json.dumps(data))
            with self.assertLogs("block-blast", logging.ERROR):
                return cards.load_cards(Path(folder))

    def test_bad_files_skipped(self):
        loaded = self.load({
            "good": {"name": "Good", "cost": 1, "tiles": ["##"], "symbols": [".C"]},
            "mixed": {"name": "Mixed", "cost": 1, "tiles": ["#g"], "symbols": ["CC"]},
            "grey-ok": {"name": "Grey", "cost": 1, "tile": "grey", "tiles": ["##"], "symbols": ["A."]},
            "apart-ok": {"name": "Apart", "cost": 1, "tiles": ["#.#"]},
            "bad-big": {"name": "Bad", "cost": 1, "tiles": ["######"]},
            "bad-tile-letter": {"name": "Bad", "cost": 1, "tiles": ["Q"]},
            "bad-symbol-letter": {"name": "Bad", "cost": 1, "tiles": ["#"], "symbols": ["Z"]},
            "bad-symbol-on-nothing": {"name": "Bad", "cost": 1, "tiles": ["#."], "symbols": [".C"]},
            "bad-symbol-size": {"name": "Bad", "cost": 1, "tiles": ["##"], "symbols": ["C"]},
            "bad-ragged": {"name": "Bad", "cost": 1, "tiles": ["##", "#"]},
            "bad-empty": {"name": "Bad", "cost": 1, "tiles": ["."]},
            "bad-name": {"cost": 1, "tiles": ["#"]},
            "bad-no-cost": {"name": "Bad", "tiles": ["#"]},
            "bad-cost": {"name": "Bad", "cost": 99, "tiles": ["#"]},
            "bad-tile-type": {"name": "Bad", "cost": 1, "tile": "lava", "tiles": ["#"]},
            "bad-play-on": {"name": "Bad", "cost": 1, "playOn": "everyone", "tiles": ["#"]},
        })
        self.assertEqual(sorted(loaded), ["apart-ok", "good", "grey-ok", "mixed"])
        self.assertEqual(loaded["mixed"]["pieces"][0], [(0, 0, "blue", "coin"), (0, 1, "grey", "coin")])
        self.assertEqual(loaded["grey-ok"]["pieces"][0], [(0, 0, "grey", "attack"), (0, 1, "grey", None)])
        self.assertEqual(cards.public(loaded["good"])["rotations"][0], {"tiles": ["bb"], "symbols": [".C"]})

    def test_counts_skip_unknown_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "deck.json")
            path.write_text(json.dumps({"dagger": 2, "nope": 1, "pair": -1}))
            with self.assertLogs("block-blast", logging.ERROR):
                counts = cards.load_counts(path, cards.CARDS)
        self.assertEqual(counts, {"dagger": 2})
        self.assertEqual(cards.deck_ids(counts), ["dagger", "dagger"])


if __name__ == "__main__":
    unittest.main()

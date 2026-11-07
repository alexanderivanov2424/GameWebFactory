"""Block Blast: tile types, symbols, the card loader and the real card files."""

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


class RealFilesTests(unittest.TestCase):
    def test_all_cards_load(self):
        self.assertEqual(len(cards.CARDS), 35)
        self.assertEqual(sum(cards.STARTING_DECK.values()), 6)
        self.assertEqual(sum(cards.BONUS_DECK.values()), 49)
        goblins = [c for c in cards.CARDS.values() if c["tile"] == "goblin"]
        self.assertEqual(len(goblins), 6)
        self.assertTrue(all(c["playOn"] == "opponent" and c["exile"] for c in goblins))
        for card in goblins:  # purple tiles with the decorative goblin face, which isn't counted
            self.assertEqual({(t, s) for _, _, t, s in card["pieces"][0]}, {("goblin", "goblin")})
            self.assertEqual(card["symbols"], {})
        self.assertTrue(all(c["id"] in cards.BONUS_DECK for c in goblins))
        self.assertFalse(set(cards.STARTING_DECK) & set(cards.BONUS_DECK))

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

    def test_symbol_counts(self):
        self.assertEqual(cards.CARDS["bulwark"]["symbols"], {"shield": 2})
        self.assertEqual(cards.CARDS["pair"]["symbols"], {"coin": 1, "attack": 1})
        self.assertEqual(cards.CARDS["square"]["symbols"], {"shield": 1})  # the starter with a shield
        self.assertEqual(cards.CARDS["bar-4"]["symbols"], {"shield": 1})
        self.assertEqual(cards.CARDS["bar-3"]["symbols"], {})
        self.assertEqual(cards.CARDS["goblin-pair"]["symbols"], {})  # the goblin face is decorative

    def test_siege_cards(self):
        siege = [c for c in cards.CARDS.values() if "siege" in c["symbols"]]
        self.assertEqual(len(siege), 3)
        for card in siege:
            self.assertEqual(card["symbols"], {"siege": 3})
            self.assertEqual(card["sizes"][0], (4, 4))
            self.assertTrue(card["exile"] and card["loose"])
            self.assertEqual({t for _, _, t, _ in card["pieces"][0]}, {"grey"})
            cells = positions(card["pieces"][0])
            for r, c in cells:  # no two siege tiles touch
                self.assertFalse({(r + 1, c), (r, c + 1)} & cells, card["id"])
        exiled = {c["id"] for c in cards.CARDS.values() if c["exile"]}
        self.assertEqual(exiled, {c["id"] for c in cards.CARDS.values() if c["tile"] == "goblin"} | {c["id"] for c in siege})


class LoaderTests(unittest.TestCase):
    def load(self, files):
        with tempfile.TemporaryDirectory() as folder:
            for name, data in files.items():
                Path(folder, f"{name}.json").write_text(json.dumps(data))
            with self.assertLogs("block-blast", logging.ERROR):
                return cards.load_cards(Path(folder))

    def test_bad_files_skipped(self):
        loaded = self.load({
            "good": {"name": "Good", "tiles": ["##"], "symbols": [".C"]},
            "mixed": {"name": "Mixed", "tiles": ["#g"], "symbols": ["CC"]},
            "grey-ok": {"name": "Grey", "tile": "grey", "tiles": ["##"], "symbols": ["A."]},
            "loose-ok": {"name": "Loose", "loose": True, "tiles": ["#.#"]},
            "bad-split": {"name": "Bad", "tiles": ["#.#"]},
            "bad-big": {"name": "Bad", "tiles": ["######"]},
            "bad-tile-letter": {"name": "Bad", "tiles": ["Q"]},
            "bad-symbol-letter": {"name": "Bad", "tiles": ["#"], "symbols": ["Z"]},
            "bad-symbol-on-nothing": {"name": "Bad", "tiles": ["#."], "symbols": [".C"]},
            "bad-symbol-size": {"name": "Bad", "tiles": ["##"], "symbols": ["C"]},
            "bad-ragged": {"name": "Bad", "tiles": ["##", "#"]},
            "bad-empty": {"name": "Bad", "tiles": ["."]},
            "bad-name": {"tiles": ["#"]},
            "bad-tile-type": {"name": "Bad", "tile": "lava", "tiles": ["#"]},
            "bad-play-on": {"name": "Bad", "playOn": "everyone", "tiles": ["#"]},
        })
        self.assertEqual(sorted(loaded), ["good", "grey-ok", "loose-ok", "mixed"])
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

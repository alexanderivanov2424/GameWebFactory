"""Peruvian Silver: the card files load cleanly, and the loaders reject bad cards."""

import importlib
import json
import tempfile
import unittest
from pathlib import Path

cards = importlib.import_module("games.peruvian-silver.cards")


def write(folder, name, data):
    text = data if isinstance(data, str) else json.dumps(data)
    (Path(folder) / name).write_text(text, encoding="utf-8")


class RealCardsTests(unittest.TestCase):
    def test_real_files_load_without_errors(self):
        with self.assertNoLogs("peruvian-silver", level="ERROR"):
            hand = cards.load_hand_cards(cards.CARDS_DIR / "hand")
            deck = cards.load_deck_cards(cards.CARDS_DIR / "deck", hand)
            start = cards.load_counts(cards.CARDS_DIR / "starting-deck.json", deck, "copies", 50)
            pool = cards.load_counts(cards.CARDS_DIR / "pool.json", deck, "weight", 1000)
            marks = cards.load_marks(cards.CARDS_DIR / "marks.json")
        self.assertEqual((hand, deck, start, pool, marks), (cards.HAND_CARDS, cards.DECK_CARDS, cards.STARTING_DECK, cards.POOL, cards.MARKS))
        # Every file on disk was accepted.
        self.assertEqual(len(deck), len(list((cards.CARDS_DIR / "deck").glob("*.json"))))
        self.assertEqual(len(hand), len(list((cards.CARDS_DIR / "hand").glob("*.json"))))

    def test_real_cards_are_consistent(self):
        self.assertTrue(cards.STARTING_DECK)
        self.assertGreaterEqual(len(cards.MARKS), cards.MARK_CHOICES)
        types = {c["type"] for c in cards.HAND_CARDS.values() if c["starting"]}
        self.assertTrue({"stay", "leave"} <= types)  # the game can't start without them
        for card in cards.DECK_CARDS.values():
            if card["type"] == "charm":
                self.assertEqual(cards.DECK_CARDS[card["protects"]]["type"], "hazard")
            if card["type"] == "relic":
                self.assertIn(card["gives"], cards.HAND_CARDS)
        self.assertLessEqual(set(cards.POOL), set(cards.DECK_CARDS))

    def test_hand_cards_are_sorted_by_order(self):
        orders = [c["order"] for c in cards.HAND_CARDS.values()]
        self.assertEqual(orders, sorted(orders))

    def test_random_pool_cards_are_different_pool_cards(self):
        picked = cards.random_pool_cards(5)
        self.assertEqual(len(picked), 5)
        self.assertEqual(len(set(picked)), 5)
        self.assertLessEqual(set(picked), set(cards.POOL))


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def load_deck(self, hand=None):
        """Load the temp folder; returns (cards, error log lines)."""
        with self.assertLogs("peruvian-silver", level="ERROR") as logs:
            result = cards.load_deck_cards(self.folder, hand or {"flee": {}})
            cards.log.error("sentinel")  # assertLogs fails if nothing is logged
        return result, [line for line in logs.output if "sentinel" not in line]

    def test_good_cards_get_defaults(self):
        write(self.folder, "pinch.json", {"name": "  Pinch  ", "type": "treasure", "value": 2, "icon": "x"})
        write(self.folder, "urn.json", {"name": "Urn", "type": "pot"})
        write(self.folder, "bats.json", {"name": "Bats", "type": "hazard", "blackSquare": True, "back": "dark"})
        write(self.folder, "dog.json", {"name": "Dog", "type": "relic", "gives": "flee"})
        write(self.folder, "ruby.json", {"name": "Ruby", "type": "gem", "color": "red"})
        write(self.folder, "charm-bats.json", {"name": "Charm", "type": "charm", "protects": "bats"})
        with self.assertNoLogs("peruvian-silver", level="ERROR"):
            loaded = cards.load_deck_cards(self.folder, {"flee": {}})
        self.assertEqual(set(loaded), {"pinch", "urn", "bats", "dog", "ruby", "charm-bats"})
        self.assertEqual(loaded["pinch"]["name"], "Pinch")
        self.assertEqual(loaded["pinch"]["back"], "default")
        self.assertFalse(loaded["pinch"]["blackSquare"])
        self.assertEqual(loaded["urn"]["growth"], 5)
        self.assertEqual((loaded["bats"]["back"], loaded["bats"]["blackSquare"]), ("dark", True))

    def test_bad_deck_cards_are_skipped_and_logged(self):
        write(self.folder, "ok.json", {"name": "Ok", "type": "treasure", "value": 1})
        write(self.folder, "no-name.json", {"type": "treasure", "value": 1})
        write(self.folder, "blank-name.json", {"name": "   ", "type": "treasure", "value": 1})
        write(self.folder, "bad-type.json", {"name": "X", "type": "banana"})
        write(self.folder, "no-value.json", {"name": "X", "type": "treasure"})
        write(self.folder, "big-value.json", {"name": "X", "type": "idol", "value": 5000})
        write(self.folder, "float-value.json", {"name": "X", "type": "treasure", "value": 2.5})
        write(self.folder, "bool-value.json", {"name": "X", "type": "treasure", "value": True})
        write(self.folder, "Bad Name.json", {"name": "X", "type": "hazard"})
        write(self.folder, "list.json", [1, 2])
        write(self.folder, "broken.json", "{not json")
        write(self.folder, "bad-back.json", {"name": "X", "type": "hazard", "back": "Fancy!"})
        write(self.folder, "no-protects.json", {"name": "X", "type": "charm"})
        write(self.folder, "unknown-gives.json", {"name": "X", "type": "relic", "gives": "teleport"})
        write(self.folder, "bad-color.json", {"name": "X", "type": "gem", "color": "green"})
        write(self.folder, "bad-growth.json", {"name": "X", "type": "pot", "growth": -1})
        write(self.folder, "charm-of-treasure.json", {"name": "X", "type": "charm", "protects": "ok"})
        write(self.folder, "charm-of-nothing.json", {"name": "X", "type": "charm", "protects": "ghost"})
        loaded, errors = self.load_deck()
        self.assertEqual(list(loaded), ["ok"])
        self.assertEqual(len(errors), 17)  # one logged reason per bad file

    def test_charm_must_protect_a_loaded_hazard(self):
        write(self.folder, "bats.json", {"name": "Bats", "type": "hazard"})
        write(self.folder, "charm-bats.json", {"name": "C", "type": "charm", "protects": "bats"})
        write(self.folder, "charm-pinch.json", {"name": "C", "type": "charm", "protects": "pinch"})
        write(self.folder, "pinch.json", {"name": "P", "type": "treasure", "value": 2})
        loaded, errors = self.load_deck()
        self.assertEqual(set(loaded), {"bats", "charm-bats", "pinch"})
        self.assertEqual(len(errors), 1)
        self.assertIn("charm-pinch", errors[0])

    def test_bad_hand_cards_are_skipped_and_sorted(self):
        write(self.folder, "leave.json", {"name": "Leave", "type": "leave", "order": 3, "starting": 1, "reusable": True})
        write(self.folder, "stay.json", {"name": "Stay", "type": "stay", "order": 1, "starting": 1})
        write(self.folder, "many.json", {"name": "X", "type": "stay", "starting": 99})
        write(self.folder, "late.json", {"name": "X", "type": "stay", "order": 5000})
        write(self.folder, "odd.json", {"name": "X", "type": "treasure"})  # a deck type
        with self.assertLogs("peruvian-silver", level="ERROR") as logs:
            loaded = cards.load_hand_cards(self.folder)
        self.assertEqual(list(loaded), ["stay", "leave"])
        self.assertEqual(len(logs.output), 3)
        self.assertTrue(loaded["leave"]["reusable"])
        self.assertFalse(loaded["stay"]["reusable"])

    def test_counts_skip_unknown_and_bad_numbers(self):
        path = self.folder / "deck.json"
        write(self.folder, "deck.json", {"a": 2, "ghost": 1, "b": -1, "c": 51, "d": True, "e": 1.5, "f": 0})
        with self.assertLogs("peruvian-silver", level="ERROR") as logs:
            counts = cards.load_counts(path, {k: {} for k in "abcdef"}, "copies", 50)
        self.assertEqual(counts, {"a": 2})
        self.assertEqual(len(logs.output), 5)

    def test_counts_not_an_object_or_missing(self):
        write(self.folder, "list.json", [1])
        with self.assertLogs("peruvian-silver", level="ERROR"):
            self.assertEqual(cards.load_counts(self.folder / "list.json", {}, "copies", 50), {})
        with self.assertLogs("peruvian-silver", level="ERROR"):
            self.assertEqual(cards.load_counts(self.folder / "nope.json", {}, "copies", 50), {})

    def test_marks(self):
        write(self.folder, "ok.json", {"emoji": ["a", "b", "c", "a", "d"]})
        self.assertEqual(cards.load_marks(self.folder / "ok.json"), ["a", "b", "c", "d"])  # duplicates dropped
        for name, data in (
            ("few.json", {"emoji": ["a", "a", "b"]}),
            ("kind.json", {"emoji": "abc"}),
            ("long.json", {"emoji": ["a", "b", "x" * 9]}),
            ("list.json", ["a", "b", "c"]),
        ):
            write(self.folder, name, data)
            with self.assertLogs("peruvian-silver", level="ERROR"):
                self.assertEqual(cards.load_marks(self.folder / name), [], name)


if __name__ == "__main__":
    unittest.main()

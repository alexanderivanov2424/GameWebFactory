"""Deck: draw, discard, reshuffle, add."""

import random
import unittest

from gamekit import Deck


class DeckTests(unittest.TestCase):
    def test_instances_have_unique_uids(self):
        deck = Deck(["a", "a", "b"], rng=random.Random(1))
        cards = deck.draw(3)
        self.assertEqual(sorted(c["card"] for c in cards), ["a", "a", "b"])
        self.assertEqual(len({c["uid"] for c in cards}), 3)
        self.assertEqual(len(deck), 0)

    def test_reshuffles_discard_when_empty(self):
        deck = Deck(["a", "b"], rng=random.Random(1))
        first = deck.draw(2)
        deck.discard(first)
        self.assertEqual(deck.counts(), {"draw": 0, "discard": 2})
        again = deck.draw(1)
        self.assertEqual(len(again), 1)
        self.assertEqual(deck.counts(), {"draw": 1, "discard": 0})

    def test_draws_fewer_when_both_piles_empty(self):
        deck = Deck(["a"], rng=random.Random(1))
        self.assertEqual(len(deck.draw(3)), 1)
        self.assertEqual(deck.draw(2), [])

    def test_add_goes_to_discard_or_draw(self):
        deck = Deck([], rng=random.Random(1))
        bought = deck.add("x")
        self.assertEqual(deck.discard_pile, [bought])
        deck.add("y", to="draw")
        self.assertEqual(deck.counts(), {"draw": 1, "discard": 1})
        self.assertNotEqual(bought["uid"], deck.draw_pile[0]["uid"])


if __name__ == "__main__":
    unittest.main()

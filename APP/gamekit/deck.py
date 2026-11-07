"""Deck: a shuffled draw pile and a discard pile of card instances (deck-building, goods decks...).

Each physical card is an instance {"uid": n, "card": card_id}: the uid tells two copies of
the same card apart (per-copy state, "discard exactly this one"), card_id points at the card
definition. Uids are unique within one Deck.

    deck = Deck(["funding", "funding", "patrol"], rng=random.Random(1))  # shuffled
    hand = deck.draw(3)        # list of instances; reshuffles the discard pile into the draw
                               # pile when it runs out (fewer cards if both are empty)
    deck.discard(hand)         # instances back on the discard pile (any iterable)
    card = deck.add("barrier") # a new instance on the discard pile (a bought card); returned
    card = deck.add("x", to="draw")  # ...or shuffled into the draw pile instead
    len(deck)                  # cards in the draw pile
    deck.draw_pile / deck.discard_pile   # the lists themselves (top of the draw pile = end)
    deck.counts()              # {"draw": n, "discard": m} for the public state

Cards in hands, on the table or in ships are the game's own business: the Deck only knows
the two piles, so remember to discard() what leaves play.
"""

import itertools
import random


class Deck:
    def __init__(self, card_ids=(), rng=random):
        self.rng = rng
        self._uids = itertools.count(1)
        self.draw_pile = [self.make(card_id) for card_id in card_ids]
        self.discard_pile = []
        rng.shuffle(self.draw_pile)

    def make(self, card_id):
        """A new instance of card_id that isn't in any pile yet."""
        return {"uid": next(self._uids), "card": card_id}

    def __len__(self):
        return len(self.draw_pile)

    def draw(self, count=1):
        drawn = []
        for _ in range(count):
            if not self.draw_pile:
                if not self.discard_pile:
                    break
                self.draw_pile, self.discard_pile = self.discard_pile, []
                self.rng.shuffle(self.draw_pile)
            drawn.append(self.draw_pile.pop())
        return drawn

    def discard(self, cards):
        self.discard_pile.extend(cards)

    def add(self, card_id, to="discard"):
        card = self.make(card_id)
        if to == "draw":
            self.draw_pile.append(card)
            self.rng.shuffle(self.draw_pile)
        else:
            self.discard_pile.append(card)
        return card

    def counts(self):
        return {"draw": len(self.draw_pile), "discard": len(self.discard_pile)}

"""Block Blast: the bank, a row of SLOTS face-up cards dealt from the bonus deck.

A card's price is its slot number counting from 1 (slot 0 costs 1 gold, slot 4 costs 5). A bought slot
stays empty until the end of the turn; then refill() shifts the remaining cards towards slot 0
and deals new cards into the last slots (fewer once the bonus deck runs out).

    bank = Bank(card_ids, rng)        shuffled bonus deck; deals SLOTS cards
    bank.slots                        [instance {"uid", "card"} or None, ...]
    bank.price(slot)                  gold to buy that slot
    bank.take(slot)                   removes and returns the instance (None if empty)
    bank.refill()                     compact, then deal into the empty slots at the end
    len(bank.deck)                    cards left in the bonus deck
"""

from gamekit import Deck

SLOTS = 5


class Bank:
    def __init__(self, card_ids, rng):
        self.deck = Deck(card_ids, rng)  # Nothing is ever discarded into it: it only shrinks.
        self.slots = [None] * SLOTS
        self.refill()

    @staticmethod
    def price(slot):
        return slot + 1

    def take(self, slot):
        card, self.slots[slot] = self.slots[slot], None
        return card

    def refill(self):
        cards = [card for card in self.slots if card is not None]
        cards += self.deck.draw(SLOTS - len(cards))
        self.slots = cards + [None] * (SLOTS - len(cards))

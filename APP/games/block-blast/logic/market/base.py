"""Block Blast: Market, the base of every market type (see market/__init__.py).

A market is a row of `size` face-up slots dealt from the shuffled bonus deck (a gamekit Deck
that only shrinks: bought and removed cards never come back). A slot holds a card instance
{"uid", "card"} or None (bought or removed this turn: refill() runs at the end of each turn).

    market = SomeMarket(card_ids, rng, size, cards)    deals the first slots
    market.slots                  [instance or None, ...]
    market.price(slot)            gold to buy that slot's card (subclass)
    market.take(slot)             removes and returns the instance (None if empty)
    market.refill()               end of turn: fill the empty slots (subclass decides how)
    market.public()               {"type", "label", "canRemove", "slots": [None | {"uid", "card",
                                  "price"}], "deck": cards left in the bonus deck}

A subclass declares:
    KEY, LABEL                    setting value and the name players read ("Conveyor Market")
    SIZE_SETTING                  the lobby setting holding its size; DEFAULT_SIZE, MAX_SIZE
    CAN_REMOVE                    players may remove a card instead of buying (Match.market_remove)
    RULES                         one line for the lobby's setting hint
"""

from gamekit import Deck


class Market:
    KEY = LABEL = SIZE_SETTING = RULES = None
    DEFAULT_SIZE = MAX_SIZE = None
    CAN_REMOVE = False

    def __init__(self, card_ids, rng, size, cards):
        self.cards = cards  # card definitions (cards.CARDS), for prices that depend on the card
        self.deck = Deck(card_ids, rng)
        self.slots = [None] * size
        self.refill()

    def price(self, slot):
        raise NotImplementedError

    def refill(self):
        raise NotImplementedError

    def take(self, slot):
        card, self.slots[slot] = self.slots[slot], None
        return card

    def public(self):
        return {
            "type": self.KEY,
            "label": self.LABEL,
            "canRemove": self.CAN_REMOVE,
            "slots": [
                None if card is None else {"uid": card["uid"], "card": card["card"], "price": self.price(i)}
                for i, card in enumerate(self.slots)
            ],
            "deck": len(self.deck),
        }

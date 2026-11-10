"""Bastion 2: the shared market.

Two parts: cards that are always for sale (unlimited: content "market": "always") and the shop,
SHOP_SIZE face-up slots dealt from a shuffled shop deck (content "market": "shop", "copies" each).
A bought shop card is replaced from the shop deck; once it's empty the slot stays empty.

    market = Market(rng)
    market.always          [card id]
    market.slots           [card id or ""]
    market.left()          cards left in the shop deck
    market.take(slot)      the card in that slot (refilled), or raises LobbyError
"""

from gamekit.validate import LobbyError

from .content import MARKET_ALWAYS, MARKET_SHOP

SHOP_SIZE = 3


class Market:
    def __init__(self, rng, always=None, shop=None):
        self.always = list(MARKET_ALWAYS if always is None else always)
        shop = MARKET_SHOP if shop is None else shop
        self.deck = [cid for cid, n in shop.items() for _ in range(n)]
        rng.shuffle(self.deck)
        self.slots = [self.deck.pop() if self.deck else "" for _ in range(SHOP_SIZE)]

    def left(self):
        return len(self.deck)

    def take(self, slot):
        if not 0 <= slot < len(self.slots) or not self.slots[slot]:
            raise LobbyError("That shop slot is empty.")
        card = self.slots[slot]
        self.slots[slot] = self.deck.pop() if self.deck else ""
        return card

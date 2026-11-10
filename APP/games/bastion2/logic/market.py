"""Bastion 2: the shared market.

Two parts: cards that are always for sale (unlimited: content "market": "always") and the shop,
SHOP_SIZE face-up slots dealt from a shuffled shop deck (content "market": "shop", "copies" each).
A bought shop card is replaced from the shop deck; once it's empty the slot stays empty.

    market = Market(rng)
    market.always          [card id]
    market.slots           [card id or ""]
    market.left()          cards left in the shop deck
    market.peek(slot)      the card in that slot, or raises LobbyError
    market.take(slot)      the card in that slot (refilled), or raises LobbyError
    market.put_back(slot, card, refill)   undo a take: the card goes back to its slot if the slot
                           still shows `refill` (which goes back on top of the shop deck), else on
                           top of the shop deck
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

    def peek(self, slot):
        if not 0 <= slot < len(self.slots) or not self.slots[slot]:
            raise LobbyError("That shop slot is empty.")
        return self.slots[slot]

    def take(self, slot):
        card = self.peek(slot)
        self.slots[slot] = self.deck.pop() if self.deck else ""
        return card

    def put_back(self, slot, card, refill):
        if 0 <= slot < len(self.slots) and self.slots[slot] == refill:
            if refill:
                self.deck.append(refill)
            self.slots[slot] = card
        else:
            self.deck.append(card)

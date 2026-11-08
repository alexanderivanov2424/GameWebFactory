"""Gilded Trail: the market (6 face-up slots) and the reserve (every other card for sale).

    market = Market(cards)          # cards: content.CARDS
    market.available(card_id)       # None if it can be bought now, else the reason
    market.gain(card_id, bought)    # one copy leaves the supply (see the rules below)
    market.public()                 # {"slots": [id or ""], "supply": {id: copies left}}

Rules:
- START_MARKET fills the 6 slots; each card for sale has COPIES copies.
- A card in a slot can be bought while copies are left. When its last copy goes, the slot
  becomes empty ("" in public()).
- Reserve cards (not in a slot) can only be bought while a slot is empty; buying one moves
  that card into the empty slot.
- The Courier's free card (bought=False) can be any card with copies left, market or reserve,
  even with no empty slot; it isn't a purchase, so it never moves a card into a slot.
"""

from gamekit import LobbyError

START_MARKET = ["tracker", "bushwhacker", "riverboat", "sketch-artist", "handyman", "courier"]
COPIES = 3


class Market:
    def __init__(self, cards):
        self.cards = cards
        self.for_sale = [cid for cid, card in cards.items() if "cost" in card]
        self.slots = [cid for cid in START_MARKET if cid in cards]
        self.supply = {cid: COPIES for cid in self.for_sale}

    def check(self, card_id):
        if card_id not in self.supply:
            raise LobbyError("That card isn't for sale.")
        if not self.supply[card_id]:
            raise LobbyError(f"{self.cards[card_id]['name']} is sold out.")

    def available(self, card_id):
        """None if card_id may be bought now, else why not."""
        try:
            self.check(card_id)
        except LobbyError as error:
            return str(error)
        if card_id in self.slots or "" in self.slots:
            return None
        return "Reserve cards can only be bought while a market slot is empty."

    def gain(self, card_id, bought=True):
        """Take one copy of card_id out of the supply (call available()/check() first)."""
        if bought and card_id not in self.slots:
            self.slots[self.slots.index("")] = card_id
        self.supply[card_id] -= 1
        if not self.supply[card_id] and card_id in self.slots:
            self.slots[self.slots.index(card_id)] = ""

    def public(self):
        return {"slots": list(self.slots), "supply": dict(self.supply)}

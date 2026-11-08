"""Bastion: the market between levels, a shared offer of card types anyone may buy.

    market = Market(rng)
    market.deal(after_level)   new offer: up to OFFER_SIZE different cards with cost > 0 whose
                               "unlock" <= after_level, at least NEW_PICKS of them (if any) from
                               the newest unlock reached, so new cards show up when they unlock
    market.offers              [card id, ...]
    market.price(slot)         card id and its cost (LobbyError on a bad slot)
Copies are unlimited: buying doesn't take the card from the offer, so everyone may buy the same
card. Retiring a card (removing it from your deck) costs RETIRE_COST, once per market.
"""

from gamekit import LobbyError

from .cards import CARDS

OFFER_SIZE = 6
NEW_PICKS = 2
RETIRE_COST = 1


class Market:
    def __init__(self, rng, cards=CARDS):
        self.rng = rng
        self.cards = cards
        self.offers = []

    def deal(self, after_level):
        pool = sorted(c for c, card in self.cards.items() if card["cost"] > 0 and card["unlock"] <= after_level)
        newest = max((self.cards[c]["unlock"] for c in pool), default=0)
        fresh = [c for c in pool if self.cards[c]["unlock"] == newest and newest > 1]
        picks = self.rng.sample(fresh, min(NEW_PICKS, len(fresh)))
        rest = [c for c in pool if c not in picks]
        picks += self.rng.sample(rest, min(OFFER_SIZE - len(picks), len(rest)))
        self.offers = sorted(picks, key=lambda c: (self.cards[c]["cost"], self.cards[c]["name"]))

    def price(self, slot):
        if not 0 <= slot < len(self.offers):
            raise LobbyError("That market slot is empty.")
        card_id = self.offers[slot]
        return card_id, self.cards[card_id]["cost"]

    def public(self):
        return {"offers": list(self.offers), "retireCost": RETIRE_COST}

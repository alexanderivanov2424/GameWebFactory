"""Bastion: Seat, one player's own things: their resources, units, soldiers, royal decrees, deck,
hand, ready flag and resolution prompts. Where units stand is Match.assigned (units.py); the
board's structures and roads carry their owner's pid.

    seat = Seat("p1", "Ann", color, Deck(ids, rng), stock)
    seat.stock              {resource: n} (structures.RESOURCE_IDS)
    seat.units / soldiers   workers / soldiers the player has in all (placed or not)
    seat.decrees            royal decrees left this planning phase
    seat.ready              done placing (place phase) or done planning (plan phase)
    seat.prompts            resolution: [prompt] still to answer, first = the one shown (resolution.py)
    seat.reshuffled         market halves reshuffled this round ({"blueprints", "actions"})
    seat.can_pay(cost) / seat.pay(cost, what)   cost = {resource or "decrees": n}
    seat.hand_card(uid) / take(card) / draw(n) / refill(size)
    seat.card_ids()         every card the player owns (hand + draw + discard), sorted for display
    seat.public() / seat.private()
Hand instances are {"uid", "card"} (plus "from": enemy index on cards a dormant enemy sent).
"""

from dataclasses import dataclass, field

from gamekit import Deck, LobbyError

from .cards import CARDS, amount_text

KIND_ORDER = {"build": 0, "action": 1, "curse": 2}


@dataclass
class Seat:
    pid: str
    name: str
    color: str
    deck: Deck
    stock: dict
    hand: list = field(default_factory=list)
    units: int = 0
    soldiers: int = 0
    decrees: int = 0
    ready: bool = False
    prompts: list = field(default_factory=list)
    reshuffled: set = field(default_factory=set)

    # --- paying --------------------------------------------------------------------------------

    def have(self, key):
        return self.decrees if key == "decrees" else self.stock.get(key, 0)

    def missing(self, cost):
        return [k for k, n in cost.items() if self.have(k) < n]

    def can_pay(self, cost):
        return not self.missing(cost)

    def pay(self, cost, what):
        short = self.missing(cost)
        if short:
            raise LobbyError(f"{what} needs {amount_text(cost)}; you're short of {', '.join(short)}.")
        for k, n in cost.items():
            if k == "decrees":
                self.decrees -= n
            else:
                self.stock[k] -= n

    def gain(self, amounts):
        for k, n in amounts.items():
            self.stock[k] = self.stock.get(k, 0) + n

    # --- cards ---------------------------------------------------------------------------------

    def hand_card(self, uid):
        for card in self.hand:
            if card["uid"] == uid:
                return card
        raise LobbyError("That card isn't in your hand.")

    def take(self, card):
        self.hand.remove(card)

    def draw(self, count):
        self.hand += self.deck.draw(count)

    def refill(self, size):
        self.deck.discard(self.hand)
        self.hand = []
        self.draw(size)

    def all_cards(self):
        return self.hand + self.deck.draw_pile + self.deck.discard_pile

    def card_ids(self):
        return sorted((c["card"] for c in self.all_cards()),
                      key=lambda c: (KIND_ORDER[CARDS[c]["kind"]], CARDS[c]["name"]))

    def public(self):
        return {"name": self.name, "color": self.color, "stock": dict(self.stock), "units": self.units,
                "soldiers": self.soldiers, "decrees": self.decrees, "ready": self.ready,
                "prompts": len(self.prompts), "hand": len(self.hand), **self.deck.counts(), "deck": self.card_ids()}

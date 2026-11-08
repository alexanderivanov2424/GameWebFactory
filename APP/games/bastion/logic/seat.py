"""Bastion: Seat, one player's own things: deck, hand, labor, gold and turn status.

    seat = Seat("p1", "Ann", color, Deck(STARTING_DECK, rng))
    seat.hand_card(uid)     the hand instance with that uid (LobbyError if not in hand)
    seat.refill(size)       discard the hand and draw a new one
    seat.card_ids()         every card the player owns (hand + draw + discard), sorted for display
    seat.public() / seat.private()
"""

from dataclasses import dataclass, field

from gamekit import Deck, LobbyError

from .cards import CARDS


@dataclass
class Seat:
    pid: str
    name: str
    color: str
    deck: Deck
    hand: list = field(default_factory=list)
    labor: int = 0
    gold: int = 0
    done: bool = False
    retired: bool = False  # used this market's card retirement

    def hand_card(self, uid):
        for card in self.hand:
            if card["uid"] == uid:
                return card
        raise LobbyError("That card isn't in your hand.")

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
                      key=lambda c: (CARDS[c]["kind"] == "order", CARDS[c]["labor"], CARDS[c]["name"]))

    def public(self):
        return {"name": self.name, "color": self.color, "labor": self.labor, "gold": self.gold, "done": self.done,
                "hand": len(self.hand), **self.deck.counts(), "deck": self.card_ids()}

    def private(self):
        return {"hand": [dict(c) for c in self.hand], "retired": self.retired,
                "owned": sorted(({"uid": c["uid"], "card": c["card"]} for c in self.all_cards()),
                                key=lambda c: (CARDS[c["card"]]["name"], c["uid"]))}

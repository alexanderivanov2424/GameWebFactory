"""Bastion: Seat, one player's own things: deck, hand and turn status (stockpile, soldiers and
the board are shared by the team, in Match).

    seat = Seat("p1", "Ann", color, Deck(ids, rng))
    seat.hand_card(uid)     the hand instance with that uid (LobbyError if not in hand)
    seat.take(card)         remove an instance from the hand (played: the caller discards or exiles it)
    seat.draw(n) / seat.refill(size)   draw more / discard the hand and draw a new one
    seat.card_ids()         every card the player owns (hand + draw + discard), sorted for display
    seat.public() / seat.private()
Hand instances are {"uid", "card"} plus "from" (enemy index) on cards an enemy sent.
"""

from dataclasses import dataclass, field

from gamekit import Deck, LobbyError

from .cards import CARDS

KIND_ORDER = {"build": 0, "action": 1, "curse": 2}


@dataclass
class Seat:
    pid: str
    name: str
    color: str
    deck: Deck
    hand: list = field(default_factory=list)
    done: bool = False

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
        return {"name": self.name, "color": self.color, "done": self.done, "hand": len(self.hand),
                **self.deck.counts(), "deck": self.card_ids()}

    def private(self):
        return {"hand": [dict(c) for c in self.hand]}

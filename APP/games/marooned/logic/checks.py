"""Marooned: build checks, a Secret Hitler style hand-off of hidden cards.

When a stage is full, the builder first picks a helper (any other player) without seeing a
card. Then the builder draws 3 check cards and secretly discards 1, the helper gets the
other 2 and reveals 1. Discarded cards are never shown, so either of them can lie about what
they saw. The deck's make-up is public, as is what's been revealed since the last shuffle.

    checks = CheckDeck(rng)
    check = Check(project_key, builder)      # step "helper"
    checks.start(check, helper)              # builder's hand of 3; step "discard"
    checks.discard(check, uid)               # helper's hand of 2;   step "reveal"
    card = checks.reveal(check, uid)         # the revealed card id; the check is over
    checks.public()                          # {"left", "total", "revealed"}
    CHECKS[card]["outcome"]                  # "solid" | "shaky" | "snapped"
"""

from gamekit import Deck, LobbyError

from .content import CHECKS, card_list

HAND = 3


class Check:
    def __init__(self, project, builder):
        self.project = project
        self.builder = builder
        self.helper = None
        self.step = "helper"
        self.hand = []

    def actor(self):
        return self.helper if self.step == "reveal" else self.builder

    def public(self):
        data = {"project": self.project, "builder": self.builder, "step": self.step}
        if self.helper:
            data["helper"] = self.helper
        return data


class CheckDeck:
    def __init__(self, rng):
        self.rng = rng
        self.deck = Deck(card_list(CHECKS), rng=rng)
        self.revealed = {}     # card id -> times revealed since the last shuffle

    def _card(self, hand, uid):
        for card in hand:
            if card["uid"] == uid:
                return card
        raise LobbyError("That card isn't in your hand.")

    def start(self, check, helper):
        if check.step != "helper":
            raise LobbyError("The helper is already picked.")
        if len(self.deck) < HAND:
            self.deck.draw_pile.extend(self.deck.discard_pile)
            self.deck.discard_pile = []
            self.rng.shuffle(self.deck.draw_pile)
            self.revealed = {}
        check.helper = helper
        check.hand = self.deck.draw(HAND)
        check.step = "discard"

    def discard(self, check, uid):
        if check.step != "discard":
            raise LobbyError("Not now.")
        card = self._card(check.hand, uid)
        check.hand.remove(card)
        self.deck.discard([card])
        check.step = "reveal"

    def reveal(self, check, uid):
        if check.step != "reveal":
            raise LobbyError("Not now.")
        card = self._card(check.hand, uid)
        self.deck.discard(check.hand)
        check.hand = []
        check.step = "done"
        self.revealed[card["card"]] = self.revealed.get(card["card"], 0) + 1
        return card["card"]

    def pick_any(self, check):
        """Someone left mid-check: a random card from the current hand does the job."""
        if check.step == "helper":
            return None
        card = self.rng.choice(check.hand)
        if check.step == "discard":
            check.hand.remove(card)
            self.deck.discard([card])
            check.step = "reveal"
            card = self.rng.choice(check.hand)
        return self.reveal(check, card["uid"])

    def public(self):
        return {
            "left": len(self.deck),
            "total": {card_id: card["count"] for card_id, card in CHECKS.items()},
            "revealed": dict(self.revealed),
            "cards": {card_id: {"name": c["name"], "text": c["text"], "outcome": c["outcome"]}
                      for card_id, c in CHECKS.items()},
        }

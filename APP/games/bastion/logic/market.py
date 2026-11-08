"""Bastion: the market, a shared row of cards anyone may buy at any time during a round with the
team's gold. Copies are unlimited: a bought slot is dealt a new card at once.

    market = Market(pool, rng)    pool = card ids that have a price (cards.py)
    market.slots                  [card id] (SIZE of them, fewer if the pool is smaller)
    market.take(slot) -> card id  and deals that slot a new card (LobbyError for a bad slot)
Dealing avoids a card already on offer while the pool has others.
"""

from gamekit import LobbyError

SIZE = 6


class Market:
    def __init__(self, pool, rng):
        self.pool = sorted(pool)
        self.rng = rng
        self.slots = []
        while len(self.slots) < min(SIZE, len(self.pool)):
            self.slots.append(self.deal())

    def deal(self, skip=None):
        fresh = [c for c in self.pool if c not in self.slots and c != skip]
        return self.rng.choice(fresh or self.pool)

    def take(self, slot):
        if not 0 <= slot < len(self.slots):
            raise LobbyError("There's no such card in the market.")
        card = self.slots[slot]
        self.slots[slot] = None
        self.slots[slot] = self.deal(skip=card)
        return card

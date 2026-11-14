"""Bastion: the market, two shared rows of cards anyone may buy during the planning phase with
their own gold: blueprints (kind "build") and actions. Copies are unlimited: a bought slot is
dealt a new card at once. The rows persist between rounds; each player may reshuffle each half
once per round for RESHUFFLE_COST gold (Match.reshuffle).

    HALVES                        {"blueprints": row size, "actions": row size}
    market = Market(pool, size, rng)   pool = card ids of that half that have a price (cards.py)
    market.slots                  [card id] (size of them, fewer if the pool is smaller)
    market.take(slot) -> card id  and deals that slot a new card (LobbyError for a bad slot)
    market.redeal()               deals every slot anew
Dealing avoids a card already on offer while the pool has others (with every card on offer, a
bought card is dealt back into its slot, so the row never shows duplicates).
"""

from gamekit import LobbyError

HALVES = {"blueprints": 4, "actions": 3}
RESHUFFLE_COST = 1


class Market:
    def __init__(self, pool, size, rng):
        self.pool = sorted(pool)
        self.size = size
        self.rng = rng
        self.slots = []
        self.redeal()

    def redeal(self):
        self.slots = []
        while len(self.slots) < min(self.size, len(self.pool)):
            self.slots.append(self.deal())

    def deal(self, skip=None):
        fresh = [c for c in self.pool if c not in self.slots and c != skip]
        if not fresh and skip is not None and skip not in self.slots:
            return skip  # a small pool (every card on offer): the bought card comes back
        return self.rng.choice(fresh or self.pool)

    def take(self, slot):
        if not 0 <= slot < len(self.slots):
            raise LobbyError("There's no such card in the market.")
        card = self.slots[slot]
        self.slots[slot] = None
        self.slots[slot] = self.deal(skip=card)
        return card

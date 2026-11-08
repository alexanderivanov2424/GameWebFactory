"""Block Blast: CostMarket. Any face-up card can be bought for its own cost (the card file's
"cost", cards/README.md). Instead of buying, a player may remove a card from the market: it
leaves the game, and it uses the turn's buy (Match.market_remove). Empty slots refill in place
at the end of the turn (fewer once the bonus deck runs out); cards don't move.
"""

from .base import Market


class CostMarket(Market):
    KEY = "cost"
    LABEL = "Cost Market"
    SIZE_SETTING = "costSize"
    DEFAULT_SIZE = 10
    MAX_SIZE = 20
    CAN_REMOVE = True
    RULES = "Any card for its own cost; instead of buying you may remove a card from the market."

    def price(self, slot):
        card = self.slots[slot]
        return None if card is None else self.cards[card["card"]]["cost"]

    def refill(self):
        for i, card in enumerate(self.slots):
            if card is None:
                drawn = self.deck.draw(1)
                self.slots[i] = drawn[0] if drawn else None

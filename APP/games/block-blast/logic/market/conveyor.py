"""Block Blast: ConveyorMarket. A card's price is its slot position counting from 1 (slot 0
costs 1 gold, the last slot costs `size`). A bought slot stays empty until the end of the turn;
then refill() shifts the remaining cards towards slot 0 and deals new cards into the last slots
(fewer once the bonus deck runs out). Cards can't be removed.
"""

from .base import Market


class ConveyorMarket(Market):
    KEY = "conveyor"
    LABEL = "Conveyor Market"
    SIZE_SETTING = "conveyorSize"
    DEFAULT_SIZE = 5
    MAX_SIZE = 10
    RULES = "Price = slot position (1, 2, 3...); cards shift towards slot 1 as the turn ends."

    def price(self, slot):
        return slot + 1

    def refill(self):
        size = len(self.slots)
        cards = [card for card in self.slots if card is not None]
        cards += self.deck.draw(size - len(cards))
        self.slots = cards + [None] * (size - len(cards))

"""Block Blast: the market, the shared pool of bonus cards players buy from. The host picks its
type in the lobby; every type is a Market subclass (base.py) in its own module here.

Modules:
    base.py      Market: the face-up slots dealt from the bonus deck, take(), public();
                 what a type declares (KEY, LABEL, sizes, CAN_REMOVE) and overrides
                 (price(slot), refill())
    conveyor.py  ConveyorMarket: price = slot position, shifts towards slot 1 when it refills
    cost.py      CostMarket: price = the card's own cost, any slot; a card may be removed instead
                 of buying; empty slots refill in place

    MARKETS                       {key: Market subclass} in lobby order
    DEFAULT                       the key the lobby starts with
    MAX_SIZE                      the largest size any type allows
    make(kind, size, card_ids, rng, cards)   a new market of that type

Adding a market type: a module with a Market subclass, an entry in MARKETS. The lobby settings
(type + a size per type) are built from MARKETS in server.py; the client draws any type from
game.market (slots with prices, canRemove).
"""

from .conveyor import ConveyorMarket
from .cost import CostMarket

MARKETS = {m.KEY: m for m in (ConveyorMarket, CostMarket)}
DEFAULT = ConveyorMarket.KEY
MAX_SIZE = max(m.MAX_SIZE for m in MARKETS.values())


def make(kind, size, card_ids, rng, cards):
    return MARKETS[kind](card_ids, rng, size, cards)

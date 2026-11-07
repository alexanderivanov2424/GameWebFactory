"""Block Blast: Seat, one player's side of the table (board, resources, deck and hand).

    seat = Seat(board, health, gold, deck, hand)
    seat.hand_card(uid)     the hand instance with that uid (LobbyError if it isn't there)
    seat.public()           what everyone sees (hand and draw pile only as counts)
    seat.private()          what only the player sees: the hand, the draw pile's contents (sorted,
                            not its order)

Fields: board (board.py), health, gold, shield (blocks that much damage, then used up; -1 at the
start of the player's turn), chapels (card removals to spend), siege (progress towards the next
strength), strength (+that much damage to each attack), target (public id the attacks hit),
out (knocked out or left), left (left the game), deck (gamekit.Deck of the player's own card
instances) and hand (instances drawn from it).
"""

from dataclasses import dataclass, field

from gamekit import Deck, LobbyError

from . import board as boards


@dataclass
class Seat:
    board: list
    health: int
    gold: int
    deck: Deck
    hand: list = field(default_factory=list)
    shield: int = 0
    chapels: int = 0
    siege: int = 0
    strength: int = 0
    target: str = None
    out: bool = False
    left: bool = False

    def hand_card(self, uid):
        card = next((c for c in self.hand if c["uid"] == uid), None)
        if card is None:
            raise LobbyError("That card isn't in your hand.")
        return card

    def public(self):
        return {
            "board": boards.public(self.board),  # {"tiles": [...], "symbols": [...]}
            "health": self.health,
            "gold": self.gold,
            "shield": self.shield,
            "chapels": self.chapels,
            "siege": self.siege,
            "strength": self.strength,
            "target": self.target,
            "out": self.out,
            "left": self.left,
            "hand": len(self.hand),
            **self.deck.counts(),  # "draw", "discard"
        }

    def private(self):
        return {
            "hand": [dict(card) for card in self.hand],
            "drawPile": sorted(card["card"] for card in self.deck.draw_pile),  # contents, not order
        }

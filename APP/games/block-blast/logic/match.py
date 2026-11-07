"""Block Blast: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, {"health": 10})
    match.turn()                          public id of the player to act, or None once over
    match.place(pid, uid, rotation, row, col, board=None)
                                          play a hand card as its shape, on your own board, or for
                                          a goblin card on `board`, an opponent still in
    match.patch(pid, uid, row, col)       discard a hand card for a blank 1x1 tile
    match.buy(pid, slot)                  buy a bank card (to the discard pile; BUYS_PER_TURN a turn)
    match.aim(pid, target)                choose whom your attacks hit (any time, not just your turn)
    match.remove_card(pid, uid)           spend a chapel token: a hand card leaves your deck for good
                                          (any time, not just your turn)
    match.end_turn(pid)                   refill the hand, refill the bank, next player
    match.remove(pid)                     pid left mid-game
    match.public() / match.private(pid)   what clients see
    match.result                          None while playing; then {"winner": pid or None, "reason"}

Each action raises LobbyError if it isn't allowed and changes nothing in that case.
Seats (self.seats[pid]): board (board.py), health, gold, shield (blocks that much damage, then
used up; -1 at the start of the player's turn), chapels (card removals to spend), siege
(progress towards the next strength), strength (+that much damage to each attack), target, out,
left, deck (gamekit.Deck of the player's own card instances) and hand (instances drawn from it).
"""

import random

from gamekit import Deck, LobbyError, TurnQueue

from . import board as boards
from . import cards as card_defs
from . import symbols, tiles
from .bank import Bank
from .cards import BONUS_DECK, CARDS, STARTING_DECK, deck_ids
from .effects import SIEGE_PER_STRENGTH, resolve_clears

HAND_SIZE = 3
BUYS_PER_TURN = 1
PATCH = [(0, 0, tiles.DEFAULT_TILE, None)]  # the blank 1x1 tile placed by discarding a card
LOG_SENT = 60  # newest log entries in the public state


class Match:
    def __init__(self, names, settings, rng=random, cards=CARDS, starting=STARTING_DECK, bonus=BONUS_DECK):
        self.names = dict(names)  # public id -> name, fixed at the start (the log stays readable)
        self.cards = cards
        self.order = list(self.names)  # seating order = turn order
        rng.shuffle(self.order)
        self.queue = TurnQueue(self.order)  # cost 1 per turn = round-robin
        self.seats = {}
        for place, pid in enumerate(self.order):
            deck = Deck(deck_ids(starting), rng)
            self.seats[pid] = {
                "board": boards.new_board(),
                "health": settings["health"],
                "gold": place + 1,  # later in the turn order = more starting gold
                "shield": 0,
                "chapels": 0,
                "siege": 0,
                "strength": 0,
                "target": None,
                "out": False,
                "left": False,
                "deck": deck,
                "hand": deck.draw(HAND_SIZE),
            }
        for pid in self.order:
            self.seats[pid]["target"] = self.next_opponent(pid)
        self.bank = Bank(deck_ids(bonus), rng)
        self.log = []
        self.step = 0  # +1 per change, for client animations
        self.turn_number = 1
        self.buys = 0  # bank cards bought this turn
        self.last_clear = None  # {"step", "pid", "cells": [[r, c], ...]}
        self.result = None
        self.add_log(None, f"{self.names[self.order[0]]} goes first.")

    def turn(self):
        return self.queue.current() if self.result is None else None

    def alive(self):
        return [pid for pid in self.order if not self.seats[pid]["out"]]

    def next_opponent(self, pid):
        """The next player still in, after pid in seating order (None if nobody is)."""
        start = self.order.index(pid)
        for i in range(1, len(self.order)):
            other = self.order[(start + i) % len(self.order)]
            if not self.seats[other]["out"]:
                return other
        return None

    def add_log(self, pid, text):
        self.step += 1
        self.log.append({"step": self.step, "pid": pid, "text": text})

    # --- Actions ------------------------------------------------------------------------------

    def require_turn(self, pid):
        if self.turn() != pid:
            raise LobbyError("It's not your turn.")

    def hand_card(self, pid, uid):
        card = next((c for c in self.seats[pid]["hand"] if c["uid"] == uid), None)
        if card is None:
            raise LobbyError("That card isn't in your hand.")
        return card

    def put_down(self, pid, card, piece, row, col, board=None, exile=False):
        """Place `piece` (board.py) on board's board (default: pid's own). The card goes to pid's
        discard pile, or with exile leaves pid's deck for good."""
        seat = self.seats[pid]
        target = self.seats[board or pid]
        if not boards.fits(target["board"], piece, row, col):
            raise LobbyError("It doesn't fit there.")
        boards.place(target["board"], piece, row, col)
        seat["hand"].remove(card)
        if not exile:
            seat["deck"].discard([card])

    def place(self, pid, uid, rotation, row, col, board=None):
        self.require_turn(pid)
        card = self.hand_card(pid, uid)
        definition = self.cards[card["card"]]
        if definition["playOn"] == "opponent":
            if board is None or board == pid or board not in self.seats or self.seats[board]["out"]:
                raise LobbyError(f"{definition['name']} goes on an opponent's board.")
        elif board not in (None, pid):
            raise LobbyError(f"{definition['name']} goes on your own board.")
        board = board or pid
        self.put_down(pid, card, definition["pieces"][rotation], row, col, board, definition["exile"])
        where = "" if board == pid else f" on {self.names[board]}'s board"
        gone = " It leaves their deck." if definition["exile"] else ""
        self.add_log(pid, f"{self.names[pid]} placed {definition['name']}{where}.{gone}")
        self.resolve_clears(board)

    def patch(self, pid, uid, row, col):
        self.require_turn(pid)
        card = self.hand_card(pid, uid)
        self.put_down(pid, card, PATCH, row, col)
        self.add_log(pid, f"{self.names[pid]} discarded {self.cards[card['card']]['name']} for a 1×1 tile.")
        self.resolve_clears(pid)

    def resolve_clears(self, pid):
        resolve_clears(self, pid)  # effects.py: spoiling and symbol effects

    def buy(self, pid, slot):
        self.require_turn(pid)
        seat = self.seats[pid]
        if self.buys >= BUYS_PER_TURN:
            raise LobbyError(f"You can only buy {BUYS_PER_TURN} card{'' if BUYS_PER_TURN == 1 else 's'} a turn.")
        card = self.bank.slots[slot]
        if card is None:
            raise LobbyError("That bank slot is empty until the end of the turn.")
        price = self.bank.price(slot)
        if seat["gold"] < price:
            raise LobbyError(f"That card costs {price} gold; you have {seat['gold']}.")
        self.bank.take(slot)
        seat["gold"] -= price
        self.buys += 1
        seat["deck"].add(card["card"])  # a new instance of the player's own, on their discard pile
        self.add_log(pid, f"{self.names[pid]} bought {self.cards[card['card']]['name']} for {price} gold.")

    def aim(self, pid, target):
        if self.result is not None:
            raise LobbyError("The game is over.")
        if self.seats[pid]["out"]:
            raise LobbyError("You're out of the game.")
        if target == pid or target not in self.seats or self.seats[target]["out"]:
            raise LobbyError("Aim at an opponent who is still in the game.")
        self.seats[pid]["target"] = target
        self.step += 1

    def remove_card(self, pid, uid):
        if self.result is not None:
            raise LobbyError("The game is over.")
        seat = self.seats[pid]
        if seat["out"]:
            raise LobbyError("You're out of the game.")
        if seat["chapels"] < 1:
            raise LobbyError("You have no card removals: clear a chapel symbol to get one.")
        card = self.hand_card(pid, uid)
        seat["hand"].remove(card)  # not discarded: it's gone from the deck for good
        seat["chapels"] -= 1
        self.add_log(pid, f"{self.names[pid]} removed {self.cards[card['card']]['name']} from their deck.")

    def end_turn(self, pid):
        self.require_turn(pid)
        seat = self.seats[pid]
        seat["hand"] += seat["deck"].draw(HAND_SIZE - len(seat["hand"]))
        self.next_turn(pid)

    def next_turn(self, pid):
        self.bank.refill()
        self.queue.advance(pid)
        self.buys = 0
        self.turn_number += 1
        starting = self.seats[self.queue.current()]
        starting["shield"] = max(0, starting["shield"] - 1)  # shields decay at the start of your turn
        self.step += 1

    # --- Leaving the game ---------------------------------------------------------------------

    def knock_out(self, pid, text):
        """pid is out (no health left, or left the game): off the turn order, others re-aim."""
        self.seats[pid]["out"] = True
        self.add_log(None, text)
        if pid in self.queue:
            if self.queue.current() == pid and self.result is None:
                self.next_turn(pid)
            self.queue.remove(pid)
        for other in self.alive():
            if self.seats[other]["target"] == pid:
                self.seats[other]["target"] = self.next_opponent(other)
        alive = self.alive()
        if self.result is None and len(alive) <= 1:
            winner = alive[0] if alive else None
            self.end(winner, f"{self.names[winner]} is the last one standing." if winner else "Nobody is left.")

    def remove(self, pid):
        if pid not in self.seats or self.seats[pid]["left"]:
            return
        self.seats[pid]["left"] = True
        if not self.seats[pid]["out"]:
            self.knock_out(pid, f"{self.names[pid]} left the game.")

    def end(self, winner, reason):
        self.result = {"winner": winner, "reason": reason}
        self.add_log(None, f"Game over: {reason}")

    # --- What clients see ---------------------------------------------------------------------

    def public(self):
        return {
            "names": self.names,
            "order": self.order,
            "turn": self.turn(),
            "turnNumber": self.turn_number,
            "step": self.step,
            "rules": {"boardSize": boards.SIZE, "handSize": HAND_SIZE, "buysPerTurn": BUYS_PER_TURN,
                      "siegePerStrength": SIEGE_PER_STRENGTH},
            "tileTypes": tiles.public_table(),  # code -> {"name", "spoils", "unspoilable"}
            "symbolTypes": symbols.public_table(),  # code -> name
            "buysLeft": max(0, BUYS_PER_TURN - self.buys),  # for the player whose turn it is
            "cards": {cid: card_defs.public(c) for cid, c in self.cards.items()},
            "seats": {
                pid: {
                    "board": boards.public(seat["board"]),  # {"tiles": [...], "symbols": [...]}
                    "health": seat["health"],
                    "gold": seat["gold"],
                    "shield": seat["shield"],
                    "chapels": seat["chapels"],
                    "siege": seat["siege"],
                    "strength": seat["strength"],
                    "target": seat["target"],
                    "out": seat["out"],
                    "left": seat["left"],
                    "hand": len(seat["hand"]),
                    **seat["deck"].counts(),
                }
                for pid, seat in self.seats.items()
            },
            "bank": [
                None if card is None else {"uid": card["uid"], "card": card["card"], "price": self.bank.price(i)}
                for i, card in enumerate(self.bank.slots)
            ],
            "bonusDeck": len(self.bank.deck),
            "log": self.log[-LOG_SENT:],
            "lastClear": self.last_clear,
        }

    def private(self, pid):
        seat = self.seats.get(pid)
        if seat is None:
            return None
        return {
            "hand": [dict(card) for card in seat["hand"]],
            "drawPile": sorted(card["card"] for card in seat["deck"].draw_pile),  # contents, not order
        }

"""Bastion 2: Match, one game's state and flow.

    Match(names, settings, rng=None)    names: {pid: name} in seat order; settings: {"turns"}
    match.stage      "setup" (everyone places castle, house, farm at once) then "play"
    match.round      1, 2, ... (play)
    match.mode       "together" (everyone plays their turn at once; the round ends when all are
                     done) or "order" (one player at a time, in seat order)
    match.current()  whose turn it is in "order" mode (None otherwise)
    match.seats      {pid: Seat}; match.board (Board); match.market (Market)
    match.log        [{"text", "pid", "round"}] newest last (LOG_SIZE kept)
    match.result     always None: the game is endless until the players vote to end it

Actions (raise LobbyError when not allowed):
    setup_place(pid, cell)                   your next setup piece
    play(pid, uid, cell, option, uids)       a hand card (effects.play)
    unbuild(pid, cell) / choose(pid, cell, index, on)   take back a pending build / toggle one of
                                             its optional "when built" cards
    use(pid, cell, uids)                     a built structure's action
    buy(pid, card=..., slot=...)             a market card (always-for-sale card id, or a shop
                                             slot) into your discard pile, for BUY_ACTIONS actions
    end_turn(pid, keep)                      builds complete, the play area and every hand card
                                             not in `keep` are discarded, temporary resources are
                                             cleared, then you draw HAND_SIZE cards
    leave(pid)
"""

import random

from gamekit import Deck
from gamekit.validate import LobbyError

from . import effects
from .board import Board
from .content import CARDS, STARTING_DECK, STRUCTURES
from .market import Market
from .seat import Seat

HAND_SIZE = 5
BUY_ACTIONS = 1
START_FOOD = 0
SETUP_PIECES = ("castle", "house", "farm")
COLORS = ["#c0392b", "#2471a3", "#d4ac0d", "#7d3c98"]
LOG_SIZE = 40


class Match:
    def __init__(self, names, settings, rng=None):
        self.rng = rng or random.Random()
        self.mode = settings.get("turns", "together")
        self.names = dict(names)
        self.colors = {pid: COLORS[i % len(COLORS)] for i, pid in enumerate(names)}
        self.order = list(names)
        self.board = Board()
        self.market = Market(self.rng)
        self.stage = "setup"
        self.round = 0
        self.turn_index = 0
        self.log = []
        self.log_count = 0
        self.result = None
        self.seats = {}
        for pid, name in names.items():
            ids = [cid for cid, n in STARTING_DECK["deck"].items() for _ in range(n)]
            seat = Seat(pid, name, self.colors[pid], Deck(ids, rng=self.rng))
            seat.food = START_FOOD
            seat.hand = seat.deck.draw(HAND_SIZE)
            for cid, n in STARTING_DECK["after_first_hand"].items():
                for _ in range(n):
                    seat.deck.add(cid, to="draw")
            self.seats[pid] = seat

    # --- helpers --------------------------------------------------------------------------------

    def note(self, text, pid=""):
        self.log.append({"text": text, "pid": pid, "round": self.round})
        self.log_count += 1
        del self.log[:-LOG_SIZE]

    def seat(self, pid):
        seat = self.seats.get(pid)
        if seat is None:
            raise LobbyError("You're not in this game.")
        return seat

    def current(self):
        if self.stage != "play" or self.mode != "order" or not self.order:
            return None
        return self.order[self.turn_index % len(self.order)]

    def turn_reason(self, pid):
        """Why pid can't act on their turn now ("" if they can)."""
        if pid not in self.seats:
            return "You're not in this game."
        if self.stage != "play":
            return "Finish placing your city first."
        if self.mode == "order":
            return "" if self.current() == pid else "It's not your turn."
        return "You've ended your turn: wait for the others." if self.seats[pid].done else ""

    def acting(self, pid):
        why = self.turn_reason(pid)
        if why:
            raise LobbyError(why)
        return self.seats[pid]

    # --- setup ----------------------------------------------------------------------------------

    def setup_piece(self, pid):
        seat = self.seats.get(pid)
        if self.stage != "setup" or seat is None or seat.setup >= len(SETUP_PIECES):
            return None
        return SETUP_PIECES[seat.setup]

    def setup_spots(self, pid):
        piece = self.setup_piece(pid)
        if piece is None:
            return []
        return self.board.castle_spots(pid) if piece == "castle" else self.board.build_spots(pid)

    def setup_place(self, pid, cell):
        seat = self.seat(pid)
        piece = self.setup_piece(pid)
        if piece is None:
            raise LobbyError("Your city is placed.")
        if piece == "castle":
            why = self.board.castle_reason(pid, cell)
        else:
            why = "" if cell in self.board.build_spots(pid) else "Place it next to your castle or buildings."
        if why:
            raise LobbyError(why)
        self.board.add(cell, piece, pid)
        seat.population += STRUCTURES[piece]["on_build"]["population"]
        seat.setup += 1
        if all(s.setup >= len(SETUP_PIECES) for s in self.seats.values()):
            self.start_play()

    def start_play(self):
        self.stage = "play"
        self.round = 1
        self.turn_index = 0
        self.note("Round 1 begins.")
        if self.mode == "order":
            if self.order:
                self.begin_turn(self.seats[self.current()])
        else:
            for seat in self.seats.values():
                self.begin_turn(seat)

    # --- turns ----------------------------------------------------------------------------------

    def begin_turn(self, seat):
        seat.actions = effects.actions_per_turn(self, seat)
        seat.pop_used = 0
        seat.used = set()
        seat.temp = {}
        seat.done = False

    def play(self, pid, uid, cell=None, option="", uids=()):
        effects.play(self, self.acting(pid), uid, cell, option, uids)

    def unbuild(self, pid, cell):
        effects.unbuild(self, self.acting(pid), cell)

    def choose(self, pid, cell, index, on):
        effects.choose(self.acting(pid), cell, index, on)

    def use(self, pid, cell, uids=()):
        effects.use(self, self.acting(pid), cell, uids)

    def buy_reason(self, seat):
        return "No actions left." if seat.actions < BUY_ACTIONS else ""

    def buy(self, pid, card=None, slot=None):
        seat = self.acting(pid)
        why = self.buy_reason(seat)
        if why:
            raise LobbyError(why)
        if card is not None:
            if card not in self.market.always:
                raise LobbyError("That card isn't for sale.")
        else:
            card = self.market.take(slot)
        seat.actions -= BUY_ACTIONS
        seat.deck.add(card)
        self.note(f"{seat.name} bought a {CARDS[card]['name']}.", pid)

    def end_turn(self, pid, keep=()):
        seat = self.acting(pid)
        effects.complete(self, seat)
        keep = set(keep)
        for inst in seat.play:
            if not inst.get("temp"):
                seat.deck.discard([inst])
        seat.play = []
        kept = []
        for inst in list(seat.hand):
            if inst["uid"] in keep:
                kept.append(inst)
            else:
                seat.hand.remove(inst)
                effects.discard(self, seat, inst)
        seat.temp = {}
        seat.pop_used = 0
        seat.actions = 0
        seat.used = set()
        seat.hand = [inst for inst in seat.hand if inst in kept] + seat.deck.draw(HAND_SIZE)
        seat.done = True
        self.advance()

    def advance(self):
        if self.stage != "play" or not self.order:
            return
        if self.mode == "order":
            self.turn_index += 1
            if self.turn_index >= len(self.order):
                self.turn_index = 0
                self.new_round()
            self.begin_turn(self.seats[self.current()])
        elif all(s.done for s in self.seats.values()):
            self.new_round()
            for seat in self.seats.values():
                self.begin_turn(seat)

    def new_round(self):
        self.round += 1
        self.note(f"Round {self.round} begins.")

    # --- leaving --------------------------------------------------------------------------------

    def leave(self, pid):
        seat = self.seats.pop(pid, None)
        if seat is None:
            return
        for cell in seat.pending:
            self.board.remove(cell)
        index = self.order.index(pid)
        was_current = self.current() == pid
        self.order.remove(pid)
        self.note(f"{seat.name} left the game.")
        if not self.order:
            return
        if self.stage == "setup":
            if all(s.setup >= len(SETUP_PIECES) for s in self.seats.values()):
                self.start_play()
        elif self.mode == "order":
            if index < self.turn_index:
                self.turn_index -= 1
            if self.turn_index >= len(self.order):
                self.turn_index = 0
                self.new_round()
            if was_current:
                self.begin_turn(self.seats[self.current()])
        elif all(s.done for s in self.seats.values()):
            self.new_round()
            for s in self.seats.values():
                self.begin_turn(s)

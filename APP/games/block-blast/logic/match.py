"""Block Blast: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"},
                  {"health": 10, "market": "conveyor", "conveyorSize": 5, "costSize": 10,
                   "packs": ["base", "chapel", "goblin", "siege"]})
    match.turn()                          public id of the player to act, or None once over
    match.place(pid, uid, rotation, row, col, board=None)
                                          play a hand card as its shape, on your own board, or for
                                          a goblin card on `board`, an opponent still in
    match.patch(pid, uid, row, col)       discard a hand card for a blank 1x1 tile
    match.buy(pid, slot)                  buy a market card (to the discard pile; BUYS_PER_TURN a turn)
    match.market_remove(pid, slot)        markets with CAN_REMOVE: instead of buying, a market card
                                          leaves the game (uses the turn's buy)
    match.aim(pid, target)                choose whom your attacks hit (any time, not just your turn)
    match.remove_card(pid, uid)           spend a chapel token: a hand card leaves your deck for good
                                          (any time, not just your turn)
    match.end_turn(pid)                   refill the hand, refill the market, next player
    match.leave(pid)                      pid left mid-game
    match.public() / match.private(pid)   what clients see
    match.result                          None while playing; then {"winner": pid or None, "reason"}

Each action raises LobbyError if it isn't allowed and changes nothing in that case. This class
is the only place that decides who may act when: require_turn (current player only) or
require_in (any time while still in: aim, remove_card).
Players' state is in self.seats[pid] (a Seat, seat.py); what a clear does is in effects.py; the
market (self.market) is the type the settings pick (market/, settings["market"] and the size in
that type's SIZE_SETTING), dealt from the card packs in settings["packs"] (packs.py).
"""

import random

from gamekit import Deck, LobbyError, TurnQueue

from . import board as boards
from . import cards as card_defs
from . import effects, symbols, tiles
from . import market as markets
from . import packs as card_packs
from .cards import CARDS, STARTING_DECK, deck_ids
from .seat import Seat

HAND_SIZE = 3
BUYS_PER_TURN = 1
PATCH = [(0, 0, tiles.DEFAULT_TILE, None)]  # the blank 1x1 tile placed by discarding a card
LOG_SENT = 60  # newest log entries in the public state


class Match:
    def __init__(self, names, settings, rng=random, cards=CARDS, starting=STARTING_DECK, packs=card_packs.PACKS):
        self.names = dict(names)  # public id -> name, fixed at the start (the log stays readable)
        self.cards = cards
        self.order = list(self.names)  # seating order = turn order
        rng.shuffle(self.order)
        self.queue = TurnQueue(self.order)  # cost 1 per turn = round-robin
        self.seats = {}
        for place, pid in enumerate(self.order):
            deck = Deck(deck_ids(starting), rng)
            self.seats[pid] = Seat(
                board=boards.new_board(),
                health=settings["health"],
                gold=place + 1,  # later in the turn order = more starting gold
                deck=deck,
                hand=deck.draw(HAND_SIZE),
            )
        for pid in self.order:
            self.seats[pid].target = self.next_opponent(pid)
        kind = settings["market"]
        size = settings[markets.MARKETS[kind].SIZE_SETTING]
        pool = card_packs.pool(settings["packs"], packs)  # the bonus deck: the host's packs
        self.market = markets.make(kind, size, pool, rng, cards)
        self.log = []
        self.step = 0  # +1 per change, for client animations
        self.turn_number = 1
        self.buys = 0  # market cards bought (or removed) this turn
        self.last_clear = None  # {"step", "pid", "cells": [[r, c], ...]}
        self.result = None
        self.catalog = self.static_state()  # the part of public() that never changes: built once
        self.add_log(None, f"{self.names[self.order[0]]} goes first.")

    def turn(self):
        return self.queue.current() if self.result is None else None

    def alive(self):
        return [pid for pid in self.order if not self.seats[pid].out]

    def next_opponent(self, pid):
        """The next player still in, after pid in seating order (None if nobody is)."""
        start = self.order.index(pid)
        for i in range(1, len(self.order)):
            other = self.order[(start + i) % len(self.order)]
            if not self.seats[other].out:
                return other
        return None

    def add_log(self, pid, text):
        self.step += 1
        self.log.append({"step": self.step, "pid": pid, "text": text})

    # --- Who may act --------------------------------------------------------------------------

    def require_turn(self, pid):
        """Actions only the current player may take."""
        if self.turn() != pid:
            raise LobbyError("It's not your turn.")

    def require_in(self, pid):
        """Actions allowed any time (also on other players' turns) while pid is still in."""
        if self.result is not None:
            raise LobbyError("The game is over.")
        if self.seats[pid].out:
            raise LobbyError("You're out of the game.")

    # --- Playing cards ------------------------------------------------------------------------

    def put_down(self, seat, card, piece, board, row, col, exile=False):
        """Place `piece` (board.py) with its top-left corner at (row, col) on the board of player
        `board`. The card leaves `seat`'s hand for its discard pile, or with exile for good."""
        grid = self.seats[board].board
        if not boards.fits(grid, piece, row, col):
            raise LobbyError("It doesn't fit there.")
        boards.place(grid, piece, row, col)
        seat.hand.remove(card)
        if not exile:
            seat.deck.discard([card])

    def place(self, pid, uid, rotation, row, col, board=None):
        self.require_turn(pid)
        seat = self.seats[pid]
        card = seat.hand_card(uid)
        definition = self.cards[card["card"]]
        if definition["playOn"] == "opponent":
            if board is None or board == pid or board not in self.seats or self.seats[board].out:
                raise LobbyError(f"{definition['name']} goes on an opponent's board.")
        elif board not in (None, pid):
            raise LobbyError(f"{definition['name']} goes on your own board.")
        board = board or pid
        self.put_down(seat, card, definition["pieces"][rotation], board, row, col, definition["exile"])
        where = "" if board == pid else f" on {self.names[board]}'s board"
        gone = " It leaves their deck." if definition["exile"] else ""
        self.add_log(pid, f"{self.names[pid]} placed {definition['name']}{where}.{gone}")
        self.resolve_clears(board)

    def patch(self, pid, uid, row, col):
        self.require_turn(pid)
        seat = self.seats[pid]
        card = seat.hand_card(uid)
        self.put_down(seat, card, PATCH, pid, row, col)
        self.add_log(pid, f"{self.names[pid]} discarded {self.cards[card['card']]['name']} for a 1×1 tile.")
        self.resolve_clears(pid)

    def resolve_clears(self, pid):
        """After a placement on pid's board: clear its full lines; the effects go to pid (the
        board's owner, also when an opponent's goblin completed the line)."""
        seat = self.seats[pid]
        cleared = effects.clear_lines(seat.board)
        if cleared is None:
            return
        clear = effects.apply_symbols(seat, cleared.counts)
        target = seat.target if clear.damage else None
        if target is not None:
            blocked = effects.deal_damage(self.seats[target], clear.damage)
            clear.gains.append(f"{clear.damage} damage to {self.names[target]}"
                               + (f" ({blocked} blocked by their shield)" if blocked else ""))
        lines = [effects.plural(len(cleared.rows), "row")] * bool(cleared.rows)
        lines += [effects.plural(len(cleared.cols), "column")] * bool(cleared.cols)
        text = f"{self.names[pid]} cleared {' and '.join(lines)}" + (f": {', '.join(clear.gains)}." if clear.gains else ".")
        if cleared.spoiled:
            text += f" Goblins spoiled {effects.plural(cleared.spoiled, 'line')}."
        self.add_log(pid, text)
        self.last_clear = {"step": self.step, "pid": pid, "cells": [[r, c] for r, c, _ in cleared.removed]}
        if target is not None and self.seats[target].health == 0:
            self.knock_out(target, f"{self.names[target]} is knocked out!")

    # --- Market, aim, card removal, turns -----------------------------------------------------

    def market_card(self, pid, slot):
        """Checks shared by buying and removing: pid's turn, a buy left, a card in that slot."""
        self.require_turn(pid)
        if not 0 <= slot < len(self.market.slots):
            raise LobbyError("There's no such market slot.")
        if self.buys >= BUYS_PER_TURN:
            also = " (removing one counts as a buy)" if self.market.CAN_REMOVE else ""
            raise LobbyError(f"You can only buy {effects.plural(BUYS_PER_TURN, 'card')} a turn{also}.")
        card = self.market.slots[slot]
        if card is None:
            raise LobbyError("That market slot is empty until the end of the turn.")
        return card

    def buy(self, pid, slot):
        card = self.market_card(pid, slot)
        seat = self.seats[pid]
        price = self.market.price(slot)
        if seat.gold < price:
            raise LobbyError(f"That card costs {price} gold; you have {seat.gold}.")
        self.market.take(slot)
        seat.gold -= price
        self.buys += 1
        # A new instance of the buyer's own deck (on their discard pile): uids stay per deck.
        seat.deck.add(card["card"])
        self.add_log(pid, f"{self.names[pid]} bought {self.cards[card['card']]['name']} for {price} gold.")

    def market_remove(self, pid, slot):
        if not self.market.CAN_REMOVE:
            raise LobbyError(f"The {self.market.LABEL} doesn't let you remove cards.")
        card = self.market_card(pid, slot)
        self.market.take(slot)  # out of the game
        self.buys += 1
        self.add_log(pid, f"{self.names[pid]} removed {self.cards[card['card']]['name']} from the market.")

    def aim(self, pid, target):
        self.require_in(pid)
        if target == pid or target not in self.seats or self.seats[target].out:
            raise LobbyError("Aim at an opponent who is still in the game.")
        self.seats[pid].target = target
        self.step += 1

    def remove_card(self, pid, uid):
        self.require_in(pid)
        seat = self.seats[pid]
        if seat.chapels < 1:
            raise LobbyError("You have no card removals: clear a chapel symbol to get one.")
        card = seat.hand_card(uid)
        seat.hand.remove(card)  # not discarded: it's gone from the deck for good
        seat.chapels -= 1
        self.add_log(pid, f"{self.names[pid]} removed {self.cards[card['card']]['name']} from their deck.")

    def end_turn(self, pid):
        self.require_turn(pid)
        seat = self.seats[pid]
        seat.hand += seat.deck.draw(HAND_SIZE - len(seat.hand))
        self.next_turn(pid)

    def next_turn(self, pid):
        self.market.refill()
        self.queue.advance(pid)
        self.buys = 0
        self.turn_number += 1
        starting = self.seats[self.queue.current()]
        starting.shield = max(0, starting.shield - 1)  # shields decay at the start of your turn
        self.step += 1

    # --- Leaving the game ---------------------------------------------------------------------

    def knock_out(self, pid, text):
        """pid is out (no health left, or left the game): off the turn order, others re-aim."""
        self.seats[pid].out = True
        self.add_log(None, text)
        if pid in self.queue:
            if self.queue.current() == pid and self.result is None:
                self.next_turn(pid)
            self.queue.remove(pid)
        for other in self.alive():
            if self.seats[other].target == pid:
                self.seats[other].target = self.next_opponent(other)
        alive = self.alive()
        if self.result is None and len(alive) <= 1:
            winner = alive[0] if alive else None
            self.end(winner, f"{self.names[winner]} is the last one standing." if winner else "Nobody is left.")

    def leave(self, pid):
        seat = self.seats.get(pid)
        if seat is None or seat.left:
            return
        seat.left = True
        if not seat.out:
            self.knock_out(pid, f"{self.names[pid]} left the game.")

    def end(self, winner, reason):
        self.result = {"winner": winner, "reason": reason}
        self.add_log(None, f"Game over: {reason}")

    # --- What clients see ---------------------------------------------------------------------

    def static_state(self):
        """Rules, code tables and card definitions: the same for the whole game."""
        return {
            "rules": {
                "boardSize": boards.SIZE,
                "handSize": HAND_SIZE,
                "buysPerTurn": BUYS_PER_TURN,
                "siegePerStrength": effects.SIEGE_PER_STRENGTH,
                "patch": boards.layers({(dr, dc): (t, s) for dr, dc, t, s in PATCH}, 1, 1),
            },
            "tileTypes": tiles.public_table(),  # code -> {"name", "spoils", "unspoilable", "help"}
            "symbolTypes": symbols.public_table(),  # code -> name
            "symbolHelp": dict(effects.HELP),  # name -> what it does (the client's legend)
            "cards": {cid: card_defs.public(c) for cid, c in self.cards.items()},
        }

    def deck_list(self, seat):
        """Every card the player owns, sorted by cost then name: public, but it doesn't tell which
        are in the hand, the draw pile or the discard pile."""
        card = self.cards
        return sorted(seat.card_ids(), key=lambda cid: (card[cid]["cost"], card[cid]["name"], cid))

    def public(self):
        return {
            **self.catalog,
            "names": self.names,
            "order": self.order,
            "turn": self.turn(),
            "turnNumber": self.turn_number,
            "step": self.step,
            "buysLeft": max(0, BUYS_PER_TURN - self.buys),  # for the player whose turn it is
            "seats": {pid: {**seat.public(), "deck": self.deck_list(seat)} for pid, seat in self.seats.items()},
            "market": self.market.public(),  # {"type", "label", "canRemove", "slots", "deck"}
            "log": self.log[-LOG_SENT:],
            "lastClear": self.last_clear,
        }

    def private(self, pid):
        seat = self.seats.get(pid)
        return seat.private() if seat else None

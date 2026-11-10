"""Bastion: Match, one game (no lobby, network or members). It never ends on its own: the game
goes on until everyone leaves or the players vote to end it (enemies are switched off).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start (seat order)
  Setup (match.phase "setup", one player at a time, setup.py):
    match.setup_place(pid, x, y)     your next piece: keep, then house, then farm
  Each round, everyone at the same time:
    "place"    match.place(pid, x, y) / match.unplace(pid, x, y)   a unit on / off a tile (units.py)
               match.ready(pid, done=True)   when everyone is ready -> resolution
    "resolve"  match.answer(pid, option)     your prompts, one by one (resolution.py); when every
               prompt is answered -> "plan"
    "plan"     match.play(pid, uid, x, y, to, give)   a hand card (playing.py)
               match.buy(pid, half, slot) / match.reshuffle(pid, half)   the market (market.py)
               match.ready(pid, done=True)   when everyone is ready -> end of round
  Any time:
    match.leave(pid)                 their units leave the board; their structures stay
    match.public() / match.private(pid)   see views.py
    match.result                     None while playing; {"winner": None, "victory": False, ...}
                                     once everyone has left

Round: start_round (hands refilled, ready flags and reshuffles reset) -> place -> resolve ->
start_planning (decrees from each player's buildings: the keep's 3) -> plan -> end_round:
soldiers return to their pool, each player's buildings pay their income (the keep: 1 food,
1 gold), then upkeep: every unit (workers and soldiers) eats 1 food; units that can't be fed are
lost (units.starve) -> the next round.

Constants: HAND_SIZE, START_STOCK, COLORS. Enemies: the dormant modules (foes.py, attacks.py,
combat.py, enemies.py) are not used; match.foes stays empty.
"""

import random

from gamekit import Deck, LobbyError

from . import playing, resolution, setup, units, views
from .board import Board
from .cards import CARDS, STARTING_DECK
from .maps import MAPS
from .market import HALVES, RESHUFFLE_COST, Market
from .seat import Seat
from .structures import RESOURCE_IDS

HAND_SIZE = 5
START_STOCK = {"gold": 3, "wood": 2, "stone": 2, "food": 2}
COLORS = ["#2f6fdf", "#d9482b", "#2f9e44", "#b8860b"]
PHASES = ("setup", "place", "resolve", "plan")


class Match:
    def __init__(self, names, settings, rng=random, maps=None, deck=None):
        self.names = dict(names)
        self.rng = rng
        self.settings = dict(settings)
        self.board = Board((maps or MAPS)[settings["map"]])
        self.colors = {pid: COLORS[i % len(COLORS)] for i, pid in enumerate(self.names)}
        start = [cid for cid, n in (STARTING_DECK if deck is None else deck).items() for _ in range(n)]
        self.seats = {pid: Seat(pid, name, self.colors[pid], Deck(start, rng),
                                {k: START_STOCK.get(k, 0) for k in RESOURCE_IDS})
                      for pid, name in self.names.items()}
        self.markets = {half: Market([c for c, card in CARDS.items() if card["price"] is not None
                                      and (card["kind"] == "build") == (half == "blueprints")], size, rng)
                        for half, size in HALVES.items()}
        self.foes = []
        self.round = 0
        self.phase = "setup"
        self.setup_order = setup.order(list(self.seats))
        self.setup_index = 0
        self.assigned = {}  # {(x, y): {"pid", "soldier", "new"}} (units.py)
        self.report = {"round": 0, "lines": []}  # this round's resolution (resolution.py)
        self.log = []
        self.result = None
        self.step = 0  # bumped whenever the phase or the setup player changes (client alerts)
        self.write("Setup: each player in turn places their keep, a house and a farm.")

    # --- helpers ----------------------------------------------------------------------------

    def write(self, text, pid=None):
        entry = {"text": text, "round": self.round}
        if pid:
            entry["pid"] = pid
        self.log.append(entry)

    def seat(self, pid):
        if self.result is not None:
            raise LobbyError("The game is over.")
        if pid not in self.seats:
            raise LobbyError("You're not in this game.")
        return self.seats[pid]

    def placing(self, pid):
        seat = self.seat(pid)
        if self.phase != "place":
            raise LobbyError("Units are placed at the start of a round.")
        if seat.ready:
            raise LobbyError("You're done: take it back to change your placements.")
        return seat

    def planning(self, pid):
        seat = self.seat(pid)
        if self.phase != "plan":
            raise LobbyError("Cards are played and bought in the planning phase.")
        if seat.ready:
            raise LobbyError("You're done: take it back to keep planning.")
        return seat

    # --- rounds -----------------------------------------------------------------------------

    def start_round(self):
        self.round += 1
        self.phase = "place"
        self.report = {"round": self.round, "lines": []}
        for seat in self.seats.values():
            seat.ready = False
            seat.reshuffled = set()
            seat.prompts = []
            seat.refill(HAND_SIZE)
        self.step += 1
        self.write(f"Round {self.round}: place your units.")

    def ready(self, pid, done=True):
        seat = self.seat(pid)
        if self.phase not in ("place", "plan"):
            raise LobbyError("Answer your prompts first." if self.phase == "resolve" else "Setup isn't over yet.")
        seat.ready = done
        self.check_all_ready()

    def check_all_ready(self):
        if self.result is not None or not self.seats or not all(s.ready for s in self.seats.values()):
            return
        if self.phase == "place":
            self.phase = "resolve"
            self.step += 1
            resolution.resolve(self)
        elif self.phase == "plan":
            self.end_round()

    def start_planning(self):
        self.phase = "plan"
        for seat in self.seats.values():
            seat.ready = False
            seat.decrees = sum(s.spec["decrees"] for s in self.board.owned(seat.pid) if s.built)
        self.step += 1

    def end_round(self):
        for cell in [c for c, u in self.assigned.items() if u["soldier"]]:
            del self.assigned[cell]  # soldiers always return to their pool
        for seat in self.seats.values():
            for s in self.board.owned(seat.pid):
                if s.built:
                    seat.gain(s.spec["income"])
            eaters = seat.units + seat.soldiers
            food = seat.stock.get("food", 0)
            eaten = min(food, eaters)
            seat.stock["food"] = food - eaten
            lost = units.starve(self, seat, eaters - eaten)
            starved = f"; {lost} unit{'s' if lost != 1 else ''} starved" if lost else ""
            self.write(f"Upkeep: {seat.name}'s {eaters} unit{'s' if eaters != 1 else ''} ate {eaten} food{starved}.", seat.pid)
        self.start_round()

    # --- actions (rules in setup.py, units.py, resolution.py, playing.py) ---------------------

    def setup_place(self, pid, x, y):
        setup.place(self, pid, x, y)

    def place(self, pid, x, y):
        units.place(self, pid, x, y)

    def unplace(self, pid, x, y):
        units.unplace(self, pid, x, y)

    def answer(self, pid, option):
        resolution.answer(self, pid, option)

    def play(self, pid, uid, x=None, y=None, to=None, give=None):
        playing.play(self, pid, uid, x, y, to, give)

    # --- market, leaving, the end -------------------------------------------------------------

    def market(self, half):
        if half not in self.markets:
            raise LobbyError("There's no such market.")
        return self.markets[half]

    def buy(self, pid, half, slot):
        seat = self.planning(pid)
        market = self.market(half)
        if not 0 <= slot < len(market.slots):
            raise LobbyError("There's no such card in the market.")
        card = CARDS[market.slots[slot]]
        if card["price"]:
            seat.pay({"gold": card["price"]}, card["name"])
        market.take(slot)
        seat.deck.add(card["id"])
        self.write(f"{seat.name} bought {card['name']}.", pid)

    def reshuffle(self, pid, half):
        seat = self.planning(pid)
        market = self.market(half)
        if half in seat.reshuffled:
            raise LobbyError("You already reshuffled that market this round.")
        seat.pay({"gold": RESHUFFLE_COST}, "A reshuffle")
        seat.reshuffled.add(half)
        market.redeal()
        self.write(f"{seat.name} reshuffled the {half} market.", pid)

    def leave(self, pid):
        seat = self.seats.get(pid)
        if seat is None or self.result is not None:
            self.seats.pop(pid, None)
            return
        units.lose(self, pid)
        del self.seats[pid]
        self.write(f"{seat.name} left; their units are gone (their buildings stay).")
        if not self.seats:
            return self.end("Everyone left.")
        if self.phase == "setup":
            setup.drop(self, pid)
        elif self.phase == "resolve":
            resolution.check_done(self)
        else:
            self.check_all_ready()

    def end(self, reason):
        if self.result is not None:
            return
        self.write(reason)
        self.result = {"winner": None, "victory": False, "reason": reason, "round": self.round}

    def public(self):
        return views.public(self)

    def private(self, pid):
        return views.private(self, pid)

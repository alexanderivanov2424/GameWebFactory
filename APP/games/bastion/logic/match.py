"""Bastion: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start (seat order)
  Place phase (everyone at once):
    match.place(pid, target) / match.unplace(pid, target)   one unit on / off a target (units.py)
    match.ready(pid, done=True)     done placing (False takes it back); when everyone is ready
                                    the act phase starts
  Act phase (one player at a time, match.turn(), in match.order from the first player):
    match.resolve(pid, target, tool=False, source=None)   one of your placed units acts (units.py)
    match.play(pid, uid, x=None, y=None, rotation=0, remove=())   a hand card (playing.py)
    match.buy(pid, slot)            a market card (bundle copies) into your discard pile, team gold
    match.reroll(pid)               deal the market anew for team gold (reroll_cost())
    match.place_tile(pid, kind, x, y) / match.remove_tile(pid, x, y)   road/wall tiles (tiles.py)
    match.strike(pid, foe, way, times=1) / match.raze(pid, x, y)   soldier counter (combat.py)
    match.end_turn(pid)             unresolved units are lost; the next player acts, or the round ends
  Any time:
    match.leave(pid)                pid left mid-game: their placements go; their turn passes
    match.public() / match.private(pid)   see views.py
    match.result                    None while playing; then {"winner": None, "victory", "reason", "round"}
  For bots and clients reading legal moves: match.phase ("place" | "act"), match.turn(),
    units.targets(match) (placeable now), units.free(match, pid), units.mine(match, pid),
    units.resolve_reason(match, target, tool, source), hauling.sources(match.board),
    views.build_targets(match, kind), views.action_targets(match, card), tiles.targets(match).

Shared by the team: the board, the stockpile (match.stock), soldiers, the keep, the road and
wall stocks (match.tile_stock). Each player has their own deck, hand and units (seat.py).

Round: start_round (worked flags, hauls and the reroll price reset, the market is dealt anew,
an enemy arrives if due, hands are discarded and refilled, the first player rotates in seat
order, units are handed out) -> place phase -> act phase -> end_round: the keep's income, upkeep
(food.py: the city eats; the hungry don't work next round), every active enemy makes its next
attack, the keep is checked, the next round starts.
The first enemy arrives on round peaceRounds + 1, then one every enemyGap rounds. Beating
every enemy wins; the keep at 0 health, or enemies left OVERTIME rounds after the last one
arrived, loses.
"""

import random

from gamekit import Deck, LobbyError

from . import combat, food, playing, tiles, units, views
from .attacks import strike as enemy_strike
from .board import Board
from .cards import CARDS, STARTING_DECK, amount_text
from .foes import make_foes
from .maps import MAPS, log as maps_log
from .market import REROLL_COST, Market
from .seat import Seat
from .structures import RESOURCE_IDS

HAND_SIZE = 5
START_STOCK = {"gold": 4, "wood": 6, "stone": 4, "wheat": 6, "tools": 2}
FIRST_CARD = "plan-house"  # always in the round-1 hand when the starting deck has one
OVERTIME = 6  # rounds after the last enemy arrives before the city falls anyway
COLORS = ["#2f6fdf", "#d9482b", "#2f9e44", "#b8860b"]


class Match:
    def __init__(self, names, settings, rng=random, enemies=None, maps=None, deck=None):
        self.names = dict(names)
        self.rng = rng
        self.settings = dict(settings)
        self.board = Board((maps or MAPS)[settings["map"]], maps_log)
        self.stock = {k: START_STOCK.get(k, 0) for k in RESOURCE_IDS}
        self.soldiers = 0
        self.keep_max = self.keep = settings["keepHealth"]
        self.tile_stock = {kind: 0 for kind in tiles.KINDS}
        self.colors = {pid: COLORS[i % len(COLORS)] for i, pid in enumerate(self.names)}
        start = [cid for cid, n in (deck or STARTING_DECK).items() for _ in range(n)]
        self.seats = {}
        for pid, name in self.names.items():
            seat = self.seats[pid] = Seat(pid, name, self.colors[pid], Deck(start, rng))
            seat.to_top(FIRST_CARD)
        self.foes = make_foes(len(self.seats), settings, rng, enemies)
        self.market = Market([c for c, card in CARDS.items() if card["price"] is not None], rng)
        self.round = 1
        self.phase = "place"
        self.order = []  # this round's turn order (first player first)
        self.turn_index = 0
        self.placed = {}  # {target: {pid: units}} (units.py)
        self.hungry = 0  # people the last upkeep couldn't feed
        self.eaten = {"bread": 0, "wheat": 0, "hungry": 0}  # what the last upkeep did
        self.hauled = 0  # haul resolutions this round (hauling.py)
        self.rerolls = 0  # market rerolls this round
        self.log = []
        self.result = None
        self.step = 0  # bumped whenever the phase or the acting player changes (client alerts)
        first = self.foes[0].arrives if self.foes else 0
        self.write(f"Build up your city: the first enemy comes on round {first}.")
        self.start_round()

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
            raise LobbyError("You're ready: take it back to change your placements.")
        return seat

    def acting(self, pid):
        seat = self.seat(pid)
        if self.phase != "act":
            raise LobbyError("Place your units first: everything else happens on your turn.")
        if self.turn() != pid:
            raise LobbyError(f"It's {self.names.get(self.turn(), 'someone else')}'s turn.")
        return seat

    def turn(self):
        """The pid acting now (act phase), else None."""
        if self.phase == "act" and self.turn_index < len(self.order):
            return self.order[self.turn_index]
        return None

    def pay(self, cost, what):
        missing = [k for k, n in cost.items() if self.stock.get(k, 0) < n]
        if missing:
            raise LobbyError(f"{what} needs {amount_text(cost)}; the stockpile is short of {', '.join(missing)}.")
        for k, n in cost.items():
            self.stock[k] -= n

    def structure_at(self, x, y):
        if x is None:
            raise LobbyError("Pick a building on the board.")
        uid = self.board.at.get((x, y))
        if uid is None:
            raise LobbyError("Pick a building on the board.")
        return self.board.structures[uid]

    def plagued(self):
        return [s for s in self.board.structures.values() if s.plague is not None]

    def population(self):
        return food.population(self.board)

    def last_arrival(self):
        return max((f.arrives for f in self.foes), default=0)

    def clear_gone(self):
        units.clear_gone(self)

    # --- rounds -----------------------------------------------------------------------------

    def start_round(self):
        self.rerolls = 0
        self.hauled = 0
        self.placed = {}
        if self.round > 1:
            self.market.redeal()
        for s in self.board.structures.values():
            s.worked = False
        for foe in self.foes:
            if foe.state == "coming" and foe.arrives <= self.round:
                foe.arrive(self.board, self.rng)
                self.write(f"{foe.enemy['icon']} {foe.name} arrives! Beat it: {foe.enemy['defeatText']}.")
        seated = list(self.seats)
        start = (self.round - 1) % len(seated) if seated else 0
        self.order = seated[start:] + seated[:start]
        for seat in self.seats.values():
            seat.refill(HAND_SIZE)
        total = units.hand_out(self)
        hungry = f" ({self.hungry} hungry)" if self.hungry else ""
        if self.order:
            self.write(f"Round {self.round}: {total} unit{'s' if total != 1 else ''}{hungry}; "
                       f"{self.names[self.order[0]]} goes first.")
        self.phase = "place"
        self.turn_index = 0
        self.step += 1
        self.board.version += 1

    def ready(self, pid, done=True):
        seat = self.seat(pid)
        if self.phase != "place":
            raise LobbyError("Everyone is already acting.")
        seat.ready = done
        self.check_all_ready()

    def check_all_ready(self):
        if self.result is None and self.phase == "place" and self.seats and all(s.ready for s in self.seats.values()):
            self.phase = "act"
            self.turn_index = 0
            self.step += 1

    def end_turn(self, pid):
        self.acting(pid)
        units.lose(self, pid)
        self.turn_index += 1
        self.next_turn()

    def next_turn(self):
        if self.result is not None:
            return
        self.step += 1
        if self.turn_index >= len(self.order):
            self.end_round()

    def end_round(self):
        for s in self.board.structures.values():
            for k, n in s.spec["income"].items():
                self.stock[k] += n
        people = self.population()
        self.eaten = food.upkeep(people, self.stock)
        self.hungry = self.eaten["hungry"]
        ate = ", ".join(f"{n} {k}" for k, n in self.eaten.items() if k != "hungry" and n) or "nothing"
        hungry = f"; {self.hungry} went hungry and won't work next round" if self.hungry else ""
        self.write(f"Upkeep: {people} people ate {ate}{hungry}.")
        for foe in self.foes:
            if foe.active:
                attack = foe.attack()
                self.write(f"{foe.enemy['icon']} {foe.name} — {attack['name']}: {'; '.join(enemy_strike(self, foe, attack))}.")
        if self.keep <= 0:
            return self.end(False, "The keep has fallen.")
        if self.round >= self.last_arrival() + OVERTIME and any(f.state != "defeated" for f in self.foes):
            return self.end(False, "The siege dragged on too long and the city gave up.")
        self.round += 1
        self.start_round()

    # --- units, cards, fighting (rules in units.py, playing.py, combat.py, tiles.py) ----------

    def place(self, pid, target):
        units.place(self, pid, target)

    def unplace(self, pid, target):
        units.unplace(self, pid, target)

    def resolve(self, pid, target, tool=False, source=None):
        units.resolve(self, pid, target, tool, source)

    def play(self, pid, uid, x=None, y=None, rotation=0, remove=()):
        playing.play(self, pid, uid, x, y, rotation, remove)

    def strike(self, pid, index, way, times=1):
        combat.strike(self, pid, index, way, times)

    def raze(self, pid, x, y):
        combat.raze(self, pid, x, y)

    def hurt(self, foe, amount):
        combat.hurt(self, foe, amount)

    def place_tile(self, pid, kind, x, y):
        tiles.place(self, pid, kind, x, y)

    def remove_tile(self, pid, x, y):
        tiles.remove(self, pid, x, y)

    # --- market, leaving, the end -------------------------------------------------------------

    def reroll_cost(self):
        return REROLL_COST + self.rerolls

    def reroll(self, pid):
        seat = self.acting(pid)
        cost = self.reroll_cost()
        self.pay({"gold": cost}, "A reroll")
        self.rerolls += 1
        self.market.redeal()
        self.write(f"{seat.name} rerolled the market for {cost} gold.", pid)

    def buy(self, pid, slot):
        seat = self.acting(pid)
        if not 0 <= slot < len(self.market.slots):
            raise LobbyError("There's no such card in the market.")
        card = CARDS[self.market.slots[slot]]
        self.pay({"gold": card["price"]}, card["name"])
        self.market.take(slot)
        for _ in range(card["bundle"]):
            seat.deck.add(card["id"])
        copies = f" ×{card['bundle']}" if card["bundle"] > 1 else ""
        self.write(f"{seat.name} bought {card['name']}{copies}.", pid)

    def leave(self, pid):
        seat = self.seats.get(pid)
        if seat is None or self.result is not None:
            self.seats.pop(pid, None)
            return
        acting = self.turn() == pid
        units.lose(self, pid)
        del self.seats[pid]
        self.write(f"{seat.name} left; their cards and units are gone.")
        if not self.seats:
            return self.end(False, "Everyone left.")
        index = self.order.index(pid) if pid in self.order else len(self.order)
        if pid in self.order:
            self.order.remove(pid)
        if self.phase == "place":
            self.check_all_ready()
        elif index < self.turn_index:
            self.turn_index -= 1
        elif acting:
            self.next_turn()

    def end(self, victory, reason):
        if self.result is not None:
            return
        self.write(reason)
        self.result = {"winner": None, "victory": victory, "reason": reason, "round": self.round}

    def public(self):
        return views.public(self)

    def private(self, pid):
        return views.private(self, pid)

"""Bastion: Match, one game from start to finish (no lobby, network or members).

    match = Match({"p1": "Ann", "p2": "Bob"}, settings)   # names fixed at the start
    match.play(pid, uid, x=None, y=None, rotation=0, remove=())   play a hand card: a blueprint
                                    on x, y (its top-left cell, turned `rotation` quarter turns), a
                                    targeted action on the building covering x, y, anything else as
                                    is; `remove`: the hand uids a trash card removes from the deck
    match.population()              cottages and the like (each Haul moves 1 more good per person)
    match.strike(pid, foe, way, times=1)   hurt an active enemy: way "soldiers" or "resources"
    match.raze(pid, x, y)           spend soldiers to remove an enemy blight tile
    match.buy(pid, slot)            a market card into your discard pile, for team gold
    match.end_turn(pid, done=True)  done with this round (False takes it back); when everyone
                                    is done the round ends (end_round)
    match.leave(pid)                pid left mid-game
    match.public() / match.private(pid)   see views.py
    match.result                    None while playing; then {"winner": None, "victory", "reason", "round"}

Shared by the team: the board, the stockpile (match.stock: gold and goods), soldiers and the
keep. Each player has their own deck and hand (seat.py).

Round: everyone plays at once, in any order, until all have ended the turn. Then end_round:
income (the keep's gold), every active enemy makes its next attack, the keep is checked, the
next round starts (worked flags reset), an enemy arrives if one is due, hands are refilled.
The first enemy arrives on round peaceRounds + 1, then one every enemyGap rounds. Beating
every enemy wins; the keep at 0 health, or enemies left OVERTIME rounds after the last one
arrived, loses.
"""

import random

from gamekit import Deck, LobbyError

from . import economy, views
from .attacks import strike as enemy_strike
from .board import Board
from .cards import CARDS, STARTING_DECK, amount_text
from .foes import make_foes
from .maps import MAPS, log as maps_log
from .market import Market
from .seat import Seat
from .structures import OUTPUT_NAMES, RESOURCE_IDS, STRUCTURES, a

HAND_SIZE = 5
START_STOCK = {"gold": 4, "wood": 4, "stone": 2}
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
        self.colors = {pid: COLORS[i % len(COLORS)] for i, pid in enumerate(self.names)}
        start = [cid for cid, n in (deck or STARTING_DECK).items() for _ in range(n)]
        self.seats = {pid: Seat(pid, name, self.colors[pid], Deck(start, rng)) for pid, name in self.names.items()}
        self.foes = make_foes(len(self.seats), settings, rng, enemies)
        self.market = Market([c for c, card in CARDS.items() if card["price"] is not None], rng)
        self.round = 1
        self.log = []
        self.result = None
        self.step = 0  # bumped every round (client alerts)
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

    def acting(self, pid):
        seat = self.seat(pid)
        if seat.done:
            raise LobbyError("You've ended your turn: take it back to act.")
        return seat

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
        return sum(s.spec["population"] for s in self.board.structures.values() if not s.ruined)

    def last_arrival(self):
        return max((f.arrives for f in self.foes), default=0)

    # --- rounds -----------------------------------------------------------------------------

    def start_round(self):
        self.step += 1
        for s in self.board.structures.values():
            s.worked = False
        for foe in self.foes:
            if foe.state == "coming" and foe.arrives <= self.round:
                foe.arrive(self.board, self.rng)
                self.write(f"{foe.enemy['icon']} {foe.name} arrives! Beat it: {foe.enemy['defeatText']}.")
        for seat in self.seats.values():
            seat.done = False
            seat.refill(HAND_SIZE)
        self.board.version += 1

    def end_turn(self, pid, done=True):
        self.seat(pid).done = done
        self.check_all_done()

    def check_all_done(self):
        if self.result is None and self.seats and all(s.done for s in self.seats.values()):
            self.end_round()

    def end_round(self):
        for s in self.board.structures.values():
            for k, n in s.spec["income"].items():
                self.stock[k] += n
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

    # --- playing cards ----------------------------------------------------------------------

    def play(self, pid, uid, x=None, y=None, rotation=0, remove=()):
        seat = self.acting(pid)
        instance = seat.hand_card(uid)
        card = CARDS[instance["card"]]
        if remove and not card["trash"]:
            raise LobbyError(f"{card['name']} doesn't remove cards.")
        if card["kind"] == "build":
            self.build(seat, instance, card, x, y, rotation)
        elif card["kind"] == "curse":
            self.pay(card["pay"], card["name"])
            seat.take(instance)  # gone from the deck for good
            self.write(f"{seat.name} paid off {card['name']}.", pid)
            foe = self.foes[instance["from"]] if "from" in instance else None
            if card["hurts"] and foe and foe.defeat.get("cards"):
                self.hurt(foe, 1, seat)
        else:
            self.action(seat, instance, card, x, y, remove)

    def build(self, seat, instance, card, x, y, rotation):
        if x is None or y is None:
            raise LobbyError("Pick where to build.")
        spec = STRUCTURES[card["structure"]]
        self.board.check(spec["id"], rotation, x, y)
        self.pay(spec["cost"], a(spec["name"]).capitalize())
        structure = self.board.place(spec["id"], rotation, x, y, seat.pid)
        seat.take(instance)
        if card["keep"]:
            seat.deck.discard([instance])
        if structure and spec["card"]:
            seat.deck.add(spec["card"])
        extra = f" (+ {CARDS[spec['card']]['name']} card)" if structure and spec["card"] else ""
        self.write(f"{seat.name} built {a(spec['name'])}{extra}.", seat.pid)

    def trashed(self, seat, instance, card, remove):
        """The hand instances a trash card removes (checked, nothing changed yet)."""
        if len(set(remove)) != len(remove) or len(remove) > card["trash"]:
            raise LobbyError(f"{card['name']} removes up to {card['trash']} different cards.")
        picked = [seat.hand_card(uid) for uid in remove]
        if instance in picked:
            raise LobbyError(f"{card['name']} can't remove itself.")
        if any(CARDS[c["card"]]["kind"] == "curse" for c in picked):
            raise LobbyError("Curses can only be paid off.")
        return picked

    def action(self, seat, instance, card, x, y, remove=()):
        target = None
        cost = dict(card["cost"])
        picked = self.trashed(seat, instance, card, remove) if card["trash"] else []
        if card["work"]:
            target = self.structure_at(x, y)
            if card["work"] != "any" and target.kind not in card["work"]:
                raise LobbyError(f"{card['name']} can't work {a(target.spec['name'])}.")
            reason = economy.why_not(self.board, target, self.stock, self.round, self.plagued())
            if reason:
                raise LobbyError(reason)
            if economy.amount(self.board, target, card) <= 0:
                raise LobbyError(f"{card['name']} would make nothing there.")
            uses = target.spec["work"]["uses"]  # paid by economy.work, after the card's own cost
            if any(self.stock[k] < cost.get(k, 0) + uses.get(k, 0) for k in set(cost) | set(uses)):
                raise LobbyError(f"The stockpile can't cover {card['name']} and the building's inputs.")
        elif card["repair"]:
            target = self.structure_at(x, y)
            for k, n in economy.repair_cost(target).items():
                cost[k] = cost.get(k, 0) + n
        elif card["cure"]:
            target = self.structure_at(x, y)
            if target.plague is None:
                raise LobbyError("That building isn't plagued.")
        self.pay(cost, card["name"])
        seat.take(instance)
        seat.deck.discard([instance])
        said = []
        for removed in picked:
            seat.take(removed)  # gone from the deck for good
        if picked:
            said.append("removed " + ", ".join(CARDS[c["card"]]["name"] for c in picked) + " from their deck")
        elif card["trash"]:
            said.append("removed nothing")
        if card["work"]:
            said.append(self.work(target, card))
        if card["repair"]:
            self.board.repair(target)
            said.append(f"repaired the {target.spec['name']}")
        if card["cure"]:
            said.append(self.cure(target))
        if card["haul"]:
            delivered, dropped = economy.haul(self.board, self.stock, card["haul"] + self.population(), card["reach"])
            text = "hauled " + (amount_text(delivered) if delivered else "nothing") + " to the stockpile"
            if dropped:
                text += f" ({amount_text(dropped)} left on the roads)"
            said.append(text)
        for k, n in card["gain"].items():
            if k == "soldiers":
                self.soldiers += n
            else:
                self.stock[k] += n
        if card["gain"]:
            said.append("gained " + amount_text(card["gain"]))
        if card["draw"]:
            seat.draw(card["draw"])
            said.append(f"drew {card['draw']}")
        if card["adds"]:
            seat.deck.add(card["adds"])
            said.append(f"took {a(CARDS[card['adds']]['name'])} card")
        self.write(f"{seat.name} played {card['name']}: {', '.join(said)}.", seat.pid)

    def work(self, s, card):
        key, amount, where = economy.work(self.board, s, self.stock, card)
        self.board.version += 1
        name = s.spec["name"]
        if key == "soldiers":
            self.soldiers += amount
        elif key == "keep":
            healed = min(amount, self.keep_max - self.keep)
            self.keep += healed
            return f"the {name} healed the keep by {healed}"
        elif key == "cure":
            cured = [self.cure(p) for p in self.plagued()[:amount]]
            return f"the {name} " + ", ".join(cured)
        stored = " (stored, waiting for a haul)" if where == "stored" else ""
        return f"the {name} made {amount} {OUTPUT_NAMES[key]}{stored}"

    def cure(self, s):
        foe = self.foes[s.plague]
        s.plague = None
        self.board.version += 1
        if foe.defeat.get("cure"):
            self.hurt(foe, 1)
        return f"cured the {s.spec['name']}"

    # --- fighting ---------------------------------------------------------------------------

    def foe(self, index):
        if not 0 <= index < len(self.foes) or not self.foes[index].active:
            raise LobbyError("That enemy isn't here.")
        return self.foes[index]

    def strike(self, pid, index, way, times=1):
        seat = self.acting(pid)
        foe = self.foe(index)
        times = min(times, foe.hp)
        if way == "soldiers" and foe.defeat.get("soldiers"):
            need = foe.defeat["soldiers"] * times
            if self.soldiers < need:
                raise LobbyError(f"That takes {need} soldiers; you have {self.soldiers}.")
            self.soldiers -= need
        elif way == "resources" and foe.defeat.get("resources"):
            self.pay({k: n * times for k, n in foe.defeat["resources"].items()}, "That")
        else:
            raise LobbyError(f"The {foe.name} can't be hurt that way.")
        self.write(f"{seat.name} hit the {foe.name} for {times}.", pid)
        self.hurt(foe, times, seat)

    def raze(self, pid, x, y):
        seat = self.acting(pid)
        blight = self.board.blights.get((x, y))
        if not blight:
            raise LobbyError("There's no enemy tile there.")
        foe = self.foes[blight["foe"]]
        cost = foe.raze if blight["lair"] else 1
        if self.soldiers < cost:
            raise LobbyError(f"Razing that takes {cost} soldier{'s' if cost > 1 else ''}; you have {self.soldiers}.")
        self.soldiers -= cost
        self.board.remove_blight((x, y))
        self.write(f"{seat.name} razed a {blight['name']}.", pid)
        if blight["lair"]:
            self.hurt(foe, 1, seat)

    def hurt(self, foe, amount, seat=None):
        if not foe.hit(amount):
            return
        for cell in [c for c, b in self.board.blights.items() if b["foe"] == foe.index]:
            self.board.remove_blight(cell)
        for s in self.board.structures.values():
            if s.plague == foe.index:
                s.plague = None
        self.board.version += 1
        self.write(f"{foe.enemy['icon']} The {foe.name} is beaten!")
        if all(f.state == "defeated" for f in self.foes):
            self.end(True, "Every enemy is beaten: the city stands!")

    # --- market, leaving, the end -------------------------------------------------------------

    def buy(self, pid, slot):
        seat = self.acting(pid)
        if not 0 <= slot < len(self.market.slots):
            raise LobbyError("There's no such card in the market.")
        card = CARDS[self.market.slots[slot]]
        self.pay({"gold": card["price"]}, card["name"])
        self.market.take(slot)
        seat.deck.add(card["id"])
        self.write(f"{seat.name} bought {card['name']}.", pid)

    def leave(self, pid):
        seat = self.seats.pop(pid, None)
        if seat is None or self.result is not None:
            return
        self.write(f"{seat.name} left; their cards are gone.")
        if not self.seats:
            self.end(False, "Everyone left.")
        else:
            self.check_all_done()

    def end(self, victory, reason):
        self.write(reason)
        self.result = {"winner": None, "victory": victory, "reason": reason, "round": self.round}

    def public(self):
        return views.public(self)

    def private(self, pid):
        return views.private(self, pid)
